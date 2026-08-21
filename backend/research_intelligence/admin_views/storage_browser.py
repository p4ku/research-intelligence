import base64
import json
import logging
import mimetypes
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote
from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import models
from django.http import HttpResponse, FileResponse, HttpResponseRedirect, Http404
from django.urls import reverse
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_sameorigin

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str, max_length: int = 120) -> str:
    """Sanitizes a string to be used safely as a downloaded filename across operating systems."""
    clean = re.sub(r'[\\/*?:"<>|]', '', name)
    clean = re.sub(r'\s+', '_', clean.strip())
    clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '', clean)
    clean = clean.strip('._-')
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip('._-')
    return clean or "document"


def _resolve_friendly_filename(target_file: str) -> str:
    """
    Resolves a human-friendly paper/document title filename instead of generic 'original.pdf'
    by looking up matching DocumentRegistry or Paper entries.
    """
    default_name = os.path.basename(target_file)
    ext = os.path.splitext(target_file)[1].lower()
    base_stem = os.path.splitext(default_name)[0]

    # Only rename generic file names like original.pdf, paper.pdf, doc.pdf or ocr_*.md
    if base_stem.lower() not in ('original', 'paper', 'doc', 'document') and not base_stem.startswith('ocr_'):
        return default_name

    try:
        from research_intelligence.models import DocumentRegistry, Paper

        # 1. Direct path lookup
        doc = DocumentRegistry.objects.filter(
            models.Q(canonical_pdf_path=target_file) | models.Q(canonical_ocr_md_path=target_file)
        ).first()

        paper = None
        if not doc:
            paper = Paper.objects.filter(
                models.Q(original_pdf_path=target_file) | models.Q(converted_md_path=target_file)
            ).first()

        # 2. Hash segment lookup (e.g. cache/documents/{sha256_hash}/original.pdf)
        if not doc and not paper:
            for part in target_file.split('/'):
                if len(part) == 64 and all(c in '0123456789abcdefABCDEF' for c in part):
                    doc = DocumentRegistry.objects.filter(sha256_hash=part).first()
                    if not doc:
                        paper = Paper.objects.filter(hash_id=part).first()
                    if doc or paper:
                        break

        title = None
        prefix = ""
        if doc:
            title = doc.title
            if doc.arxiv_id:
                prefix = f"{_sanitize_filename(doc.arxiv_id)}_"
        elif paper:
            title = paper.title
            if paper.arxiv_id:
                prefix = f"{_sanitize_filename(paper.arxiv_id)}_"

        if title:
            safe_title = _sanitize_filename(title)
            suffix = f"_{base_stem}" if base_stem.startswith('ocr_') else ""
            return f"{prefix}{safe_title}{suffix}{ext}"
    except Exception as e:
        logger.warning(f"Failed to resolve friendly filename for '{target_file}': {e}")

    return default_name


def _get_file_icon(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.pdf',):
        return '📄 PDF'
    elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
        return '🖼️ Image'
    elif ext in ('.json', '.xml', '.yaml', '.yml'):
        return '📊 Data'
    elif ext in ('.md', '.txt', '.csv'):
        return '📝 Text'
    elif ext in ('.py', '.sh', '.js', '.html', '.css'):
        return '⚙️ Code'
    return '📄 File'


def _format_size(size_bytes: int) -> str:
    if size_bytes is None:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _recursive_delete_dir(dir_path: str) -> int:
    """
    Recursively delete all files and directory structures inside dir_path in default_storage.
    Supports Local FileSystem (FileSystemStorage), AWS S3/MinIO (S3Boto3Storage), and test storage.
    """
    import shutil
    clean_dir = dir_path.strip('/')
    if not clean_dir or clean_dir in ('', 'workspaces', 'cache'):
        return 0

    deleted_count = 0

    # 1. S3 / MinIO direct bucket prefix purge if available
    if hasattr(default_storage, 'bucket') and default_storage.bucket is not None:
        try:
            prefix = clean_dir if clean_dir.endswith('/') else f"{clean_dir}/"
            objects_to_delete = default_storage.bucket.objects.filter(Prefix=prefix)
            for obj in objects_to_delete:
                obj.delete()
                deleted_count += 1
            try:
                default_storage.bucket.objects.filter(Prefix=clean_dir).delete()
            except Exception:
                pass
            return deleted_count
        except Exception as s3_err:
            logger.warning(f"S3 bucket prefix delete failed for '{clean_dir}': {s3_err}")

    # 2. Standard recursive listdir deletion
    try:
        dirs, files = default_storage.listdir(clean_dir)
        for f in files:
            full_f_path = f"{clean_dir}/{f}"
            try:
                if default_storage.exists(full_f_path):
                    default_storage.delete(full_f_path)
                    deleted_count += 1
            except Exception:
                pass
        for d in dirs:
            full_d_path = f"{clean_dir}/{d}"
            deleted_count += _recursive_delete_dir(full_d_path)
    except Exception as list_err:
        logger.warning(f"Storage listdir error during recursive delete of '{clean_dir}': {list_err}")

    # 3. Local filesystem cleanup: physically remove empty folder or folder tree from disk
    local_path = None
    if hasattr(default_storage, 'path'):
        try:
            local_path = default_storage.path(clean_dir)
        except Exception:
            pass
    if not local_path and hasattr(default_storage, 'location'):
        try:
            local_path = os.path.join(default_storage.location, clean_dir)
        except Exception:
            pass

    if local_path and os.path.exists(local_path):
        try:
            if os.path.isdir(local_path):
                shutil.rmtree(local_path, ignore_errors=True)
            elif os.path.isfile(local_path):
                os.remove(local_path)
        except Exception as fs_err:
            logger.warning(f"Local filesystem cleanup failed for '{local_path}': {fs_err}")

    # 4. Also attempt default_storage.delete on the directory name and with trailing slash
    for candidate in (clean_dir, f"{clean_dir}/"):
        try:
            if default_storage.exists(candidate):
                default_storage.delete(candidate)
        except Exception:
            pass

    return deleted_count


def _is_allowed_path(path: str) -> bool:
    """
    Ensure the path is within the allowed storage area ('workspaces', 'cache', or test folders).
    Prevents browsing, reading, or deleting codebase and system files.
    """
    clean_path = path.strip('/')
    if not clean_path:
        return True
    parts = [p for p in clean_path.split('/') if p]
    if '..' in parts:
        return False
    root_folder = parts[0]
    # Allow 'workspaces', 'cache' and test directories
    if root_folder in ('workspaces', 'cache') or root_folder.startswith('test_'):
        return True
    return False


@xframe_options_sameorigin
def storage_browser_view(request):
    """
    Django Admin custom view for browsing, previewing, downloading, and deleting files/directories in default_storage (S3/Local).
    """
    if not request.user.is_staff:
        raise Http404("Permission denied")

    current_path = request.GET.get('path', '').strip('/')

    action = request.GET.get('action', '')
    target_file = request.GET.get('file', '').strip('/')
    target_dir = request.GET.get('target_dir', '').strip('/')

    base_url = reverse('admin:storage-browser')

    # Security check: disallow browsing, previewing, downloading or deleting codebase/system files
    if not _is_allowed_path(current_path):
        messages.error(request, f"Access denied: Path '{escape(current_path)}' is outside storage root.")
        return HttpResponseRedirect(f"{base_url}?path=")

    if target_file and not _is_allowed_path(target_file):
        messages.error(request, f"Access denied: File '{escape(target_file)}' is outside storage root.")
        return HttpResponseRedirect(f"{base_url}?path={current_path}")

    if target_dir and not _is_allowed_path(target_dir):
        messages.error(request, f"Access denied: Directory '{escape(target_dir)}' is outside storage root.")
        return HttpResponseRedirect(f"{base_url}?path={current_path}")

    # Detect active Storage Backend
    storage_engine_name = default_storage.__class__.__name__
    if hasattr(default_storage, 'bucket_name'):
        storage_badge = f'<span style="background-color: #238636; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">☁️ AWS S3 Bucket ({escape(str(default_storage.bucket_name))})</span>'
    elif hasattr(default_storage, 'location'):
        storage_badge = f'<span style="background-color: #0d6efd; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">💻 Local FileSystem ({escape(str(default_storage.location))})</span>'
    else:
        storage_badge = f'<span style="background-color: #6e7681; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">📦 Storage: {escape(storage_engine_name)}</span>'

    # 1. Handle File Download or Inline Raw Stream (PDFs / Images)
    if action in ('download', 'view_raw', 'raw', 'raw_pdf') and target_file:
        if not default_storage.exists(target_file):
            messages.error(request, f"File '{target_file}' does not exist.")
            return HttpResponseRedirect(f"{base_url}?path={current_path}")
        try:
            file_obj = default_storage.open(target_file, 'rb')
            filename = _resolve_friendly_filename(target_file)
            mime_type, _ = mimetypes.guess_type(target_file)
            if target_file.lower().endswith('.pdf'):
                mime_type = 'application/pdf'
            disposition = 'attachment' if action == 'download' else 'inline'
            response = FileResponse(file_obj, content_type=mime_type or 'application/octet-stream')
            response['Content-Disposition'] = f'{disposition}; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            return response
        except Exception as e:
            messages.error(request, f"Failed to access file: {str(e)}")
            return HttpResponseRedirect(f"{base_url}?path={current_path}")

    # 2. Handle File Deletion
    if action == 'delete_file' and target_file:
        if default_storage.exists(target_file):
            try:
                default_storage.delete(target_file)
                messages.success(request, f"Successfully deleted file '<strong>{escape(target_file)}</strong>'.")
            except Exception as e:
                messages.error(request, f"Error deleting file '{target_file}': {str(e)}")
        else:
            messages.warning(request, f"File '{target_file}' was not found.")
        return HttpResponseRedirect(f"{base_url}?path={current_path}")

    # 3. Handle Directory Deletion
    if action == 'delete_dir' and target_dir:
        try:
            count = _recursive_delete_dir(target_dir)
            messages.success(request, f"Successfully deleted directory '<strong>{escape(target_dir)}</strong>' ({count} file(s) removed).")
        except Exception as e:
            messages.error(request, f"Error deleting directory '{target_dir}': {str(e)}")
        return HttpResponseRedirect(f"{base_url}?path={current_path}")

    # 4. Enumerate Directories and Files
    dirs_list = []
    files_list = []
    try:
        raw_dirs, raw_files = default_storage.listdir(current_path)
        # When browsing root (/), strictly filter to allowed storage roots (workspaces, cache, and test folders)
        # and hide root codebase files/directories.
        if not current_path:
            filtered_dirs = [d for d in raw_dirs if d in ('workspaces', 'cache') or d.startswith('test_')]
            if 'workspaces' not in filtered_dirs and (default_storage.exists('workspaces') or not filtered_dirs):
                filtered_dirs.append('workspaces')
            if 'cache' not in filtered_dirs and (default_storage.exists('cache') or default_storage.exists('cache/documents') or not filtered_dirs):
                filtered_dirs.append('cache')
            filtered_files = []
        else:
            filtered_dirs = raw_dirs
            filtered_files = raw_files

        for d in sorted(filtered_dirs):
            d_rel_path = os.path.join(current_path, d) if current_path else d
            d_mtime_str = "-"
            try:
                d_mtime = default_storage.get_modified_time(d_rel_path)
                d_mtime_str = d_mtime.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

            # Fallback for S3/MinIO virtual prefixes where directories have no direct metadata:
            # If folder name is a valid UUID, look up matching Workspace or PipelineRun timestamp
            # If folder name is a 64-character hex hash, look up DocumentRegistry timestamp
            if d_mtime_str == "-":
                try:
                    if len(d) == 36:
                        import uuid
                        if uuid.UUID(d):
                            from research_intelligence.models import Workspace, PipelineRun
                            ws = Workspace.objects.filter(id=d).only('created_at').first()
                            if ws and ws.created_at:
                                d_mtime_str = ws.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                pr = PipelineRun.objects.filter(id=d).only('created_at').first()
                                if pr and pr.created_at:
                                    d_mtime_str = pr.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    elif len(d) == 64:
                        from research_intelligence.models import DocumentRegistry
                        doc = DocumentRegistry.objects.filter(sha256_hash=d).only('created_at').first()
                        if doc and doc.created_at:
                            d_mtime_str = doc.created_at.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            dirs_list.append({
                'name': d,
                'rel_path': d_rel_path,
                'mtime_str': d_mtime_str
            })
        for f in sorted(filtered_files):
            f_rel_path = os.path.join(current_path, f) if current_path else f
            size = None
            mtime_str = "-"
            try:
                size = default_storage.size(f_rel_path)
            except Exception:
                pass
            try:
                mtime = default_storage.get_modified_time(f_rel_path)
                mtime_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

            files_list.append({
                'name': f,
                'rel_path': f_rel_path,
                'icon': _get_file_icon(f),
                'size_formatted': _format_size(size),
                'mtime_str': mtime_str
            })
    except Exception as e:
        messages.error(request, f"Error listing path '{current_path}': {str(e)}")

    # 5. Build Breadcrumbs HTML
    crumbs = [{'name': 'Root Storage (/)', 'path': ''}]
    if current_path:
        parts = current_path.split('/')
        acc = []
        for p in parts:
            acc.append(p)
            crumbs.append({'name': p, 'path': '/'.join(acc)})

    breadcrumb_html = []
    for idx, c in enumerate(crumbs):
        if idx == len(crumbs) - 1:
            breadcrumb_html.append(f"<strong>{escape(c['name'])}</strong>")
        else:
            breadcrumb_html.append(f'<a href="{base_url}?path={escape(c["path"])}">{escape(c["name"])}</a>')
    breadcrumb_nav = " / ".join(breadcrumb_html)

    # 6. Build File Preview Box if preview requested
    preview_box_html = ""
    if action == 'preview' and target_file and default_storage.exists(target_file):
        try:
            size = default_storage.size(target_file)
            ext = os.path.splitext(target_file)[1].lower()
            mime_type, _ = mimetypes.guess_type(target_file)
            friendly_name = _resolve_friendly_filename(target_file)
            friendly_display = f'<span style="color: #7ee787; margin-left: 8px; font-weight: normal;">(📥 {escape(friendly_name)})</span>' if friendly_name != os.path.basename(target_file) else ""

            extra_btn = ""
            if ext in ('.pdf',):
                raw_url = f"{base_url}?action=view_raw&file={escape(target_file)}"
                extra_btn = f'<a href="{raw_url}" target="_blank" style="display: inline-block; background-color: #0d6efd; color: #ffffff !important; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; line-height: 1.2; white-space: nowrap; margin-right: 8px;">↗️ Open Full Screen</a>'
                preview_body = f"""
                <div style="background-color: #525659; padding: 0;">
                    <iframe src="{raw_url}" style="width: 100%; height: 750px; border: none; display: block; background: #525659;" title="PDF Preview"></iframe>
                </div>
                """
            elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
                f_bytes = default_storage.open(target_file, 'rb').read()
                b64_str = base64.b64encode(f_bytes).decode('utf-8')
                mime = mime_type or 'image/png'
                preview_body = f'<div style="text-align: center; padding: 20px;"><img src="data:{mime};base64,{b64_str}" style="max-width: 100%; max-height: 500px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);" /></div>'
            elif size and size > 1024 * 1024:
                preview_body = f'<div style="padding: 20px; color: #888;">File is too large for inline preview ({_format_size(size)}). Use the download button below.</div>'
            else:
                f_bytes = default_storage.open(target_file, 'rb').read(1024 * 1024)
                try:
                    content_text = f_bytes.decode('utf-8')
                    if ext == '.json':
                        try:
                            content_text = json.dumps(json.loads(content_text), indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                    preview_body = f'<pre style="margin: 0; padding: 16px; background-color: #0d1117; color: #e6edf3; font-family: monospace; font-size: 13px; max-height: 480px; overflow: auto; border-radius: 0 0 6px 6px;"><code>{escape(content_text)}</code></pre>'
                except UnicodeDecodeError:
                    preview_body = '<div style="padding: 20px; color: #888;">Binary file preview unavailable. Download file to view.</div>'

            preview_box_html = f"""
            <div style="margin: 20px 0; border: 1px solid #30363d; border-radius: 6px; overflow: hidden; background-color: #161b22; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                <div style="padding: 10px 16px; background-color: #21262d; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; color: #f0f6fc;">
                    <div>
                        <strong>🔍 File Preview:</strong> <code style="color: #58a6ff;">{escape(target_file)}</code> ({_format_size(size)}){friendly_display}
                    </div>
                    <div>
                        {extra_btn}
                        <a href="{base_url}?path={escape(current_path)}&action=download&file={escape(target_file)}" title="Download as {escape(friendly_name)}" style="display: inline-block; background-color: #238636; color: #ffffff !important; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; line-height: 1.2; white-space: nowrap; margin-right: 8px;">⬇️ Download</a>
                        <a href="{base_url}?path={escape(current_path)}" style="display: inline-block; background-color: #6e7681; color: #ffffff !important; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; line-height: 1.2; white-space: nowrap;">✖️ Close</a>
                    </div>
                </div>
                {preview_body}
            </div>
            """
        except Exception as e:
            preview_box_html = f'<div class="errornote">Error generating preview: {escape(str(e))}</div>'

    # 7. Render Main Admin HTML Table
    rows_html = []

    # Parent directory link
    if current_path:
        parent_path = '/'.join(current_path.split('/')[:-1])
        rows_html.append(f"""
        <tr>
            <td colspan="4" style="padding: 10px 12px; background-color: #f8f9fa;">
                📁 <a href="{base_url}?path={escape(parent_path)}" style="font-weight: bold; text-decoration: none;">.. (Parent Directory)</a>
            </td>
        </tr>
        """)

    # List subdirectories
    for d in dirs_list:
        rows_html.append(f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px 12px;">
                📁 <a href="{base_url}?path={escape(d['rel_path'])}" style="font-weight: bold; font-size: 14px; text-decoration: none; color: #0d6efd;">{escape(d['name'])}/</a>
            </td>
            <td style="padding: 10px 12px; color: #6c757d;">Directory</td>
            <td style="padding: 10px 12px; color: #6c757d; font-size: 13px;">{d['mtime_str']}</td>
            <td style="padding: 10px 12px; text-align: right;">
                <a href="{base_url}?path={escape(current_path)}&action=delete_dir&target_dir={escape(d['rel_path'])}" 
                   onclick="return confirm('Are you sure you want to recursively delete directory `{escape(d['name'])}` and ALL its files?');"
                   style="color: #dc3545; font-size: 12px; text-decoration: none; padding: 3px 8px; border: 1px solid #dc3545; border-radius: 4px;">🗑️ Delete Dir</a>
            </td>
        </tr>
        """)

    # List files
    for f in files_list:
        is_pdf = f['name'].lower().endswith('.pdf')
        pdf_extra_action = ""
        if is_pdf:
            raw_url = f"{base_url}?action=view_raw&file={escape(f['rel_path'])}"
            pdf_extra_action = f'<a href="{raw_url}" target="_blank" style="color: #6f42c1; font-size: 12px; text-decoration: none; padding: 3px 8px; border: 1px solid #6f42c1; border-radius: 4px; margin-right: 4px;">↗️ New Tab</a>'

        rows_html.append(f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px 12px;">
                {f['icon']} <a href="{base_url}?path={escape(current_path)}&action=preview&file={escape(f['rel_path'])}" style="font-size: 14px; text-decoration: none; color: #212529; font-weight: {'600' if is_pdf else 'normal'};">{escape(f['name'])}</a>
            </td>
            <td style="padding: 10px 12px; color: #495057; font-size: 13px;">{f['size_formatted']}</td>
            <td style="padding: 10px 12px; color: #6c757d; font-size: 13px;">{f['mtime_str']}</td>
            <td style="padding: 10px 12px; text-align: right; white-space: nowrap;">
                {pdf_extra_action}
                <a href="{base_url}?path={escape(current_path)}&action=preview&file={escape(f['rel_path'])}" 
                   style="color: #0d6efd; font-size: 12px; text-decoration: none; padding: 3px 8px; border: 1px solid #0d6efd; border-radius: 4px; margin-right: 4px;">👁️ Preview</a>
                <a href="{base_url}?path={escape(current_path)}&action=download&file={escape(f['rel_path'])}" 
                   style="color: #198754; font-size: 12px; text-decoration: none; padding: 3px 8px; border: 1px solid #198754; border-radius: 4px; margin-right: 4px;">⬇️ Download</a>
                <a href="{base_url}?path={escape(current_path)}&action=delete_file&file={escape(f['rel_path'])}" 
                   onclick="return confirm('Are you sure you want to delete file `{escape(f['name'])}`?');"
                   style="color: #dc3545; font-size: 12px; text-decoration: none; padding: 3px 8px; border: 1px solid #dc3545; border-radius: 4px;">🗑️ Delete</a>
            </td>
        </tr>
        """)

    if not dirs_list and not files_list:
        rows_html.append("""
        <tr>
            <td colspan="4" style="padding: 24px; text-align: center; color: #6c757d; font-style: italic;">
                Directory is empty.
            </td>
        </tr>
        """)

    table_body = "\n".join(rows_html)

    # Render Django Messages
    from django.contrib.messages import get_messages
    storage_messages = get_messages(request)
    messages_html = ""
    for msg in storage_messages:
        tag = msg.tags or "info"
        bg_color = "#f8d7da" if "error" in tag else ("#d1e7dd" if "success" in tag else "#fff3cd")
        border_color = "#f5c2c7" if "error" in tag else ("#badbcc" if "success" in tag else "#ffecb5")
        text_color = "#842029" if "error" in tag else ("#0f5132" if "success" in tag else "#664d03")
        messages_html += f'<div style="margin-bottom: 12px; padding: 10px 14px; border-radius: 4px; background-color: {bg_color}; border: 1px solid {border_color}; color: {text_color}; font-size: 13px;">{mark_safe(str(msg))}</div>'

    # Render Django Admin page layout
    page_html = f"""
    <!DOCTYPE html>
    <div id="content" class="colM" style="padding: 20px;">
        <div style="margin-bottom: 16px; font-size: 16px; background: #fff; padding: 12px 16px; border-radius: 6px; border: 1px solid #dee2e6; box-shadow: 0 1px 3px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center;">
            <div>📂 <strong>Storage Browser:</strong> {breadcrumb_nav}</div>
            <div>{storage_badge}</div>
        </div>

        {messages_html}

        {preview_box_html}

        <div style="background: #fff; border-radius: 6px; border: 1px solid #dee2e6; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <table style="width: 100%; border-collapse: collapse; text-align: left; font-family: system-ui, -apple-system, sans-serif;">
                <thead>
                    <tr style="background-color: #f1f3f5; border-bottom: 2px solid #dee2e6; color: #495057; font-size: 13px;">
                        <th style="padding: 12px;">Name</th>
                        <th style="padding: 12px; width: 120px;">Size</th>
                        <th style="padding: 12px; width: 180px;">Modified</th>
                        <th style="padding: 12px; width: 260px; text-align: right;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {table_body}
                </tbody>
            </table>
        </div>
    </div>
    """

    response = HttpResponse(page_html)
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response
