import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from django.contrib import messages
from django.core.files.storage import default_storage
from django.http import HttpResponse, FileResponse, HttpResponseRedirect, Http404
from django.urls import reverse
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)


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
    """Recursively delete all files inside dir_path in default_storage."""
    deleted_count = 0
    try:
        dirs, files = default_storage.listdir(dir_path)
        for f in files:
            full_f_path = os.path.join(dir_path, f) if dir_path else f
            default_storage.delete(full_f_path)
            deleted_count += 1
        for d in dirs:
            full_d_path = os.path.join(dir_path, d) if dir_path else d
            deleted_count += _recursive_delete_dir(full_d_path)
    except Exception as e:
        logger.warning(f"Error recursively deleting directory '{dir_path}': {str(e)}")
    return deleted_count


def storage_browser_view(request):
    """
    Django Admin custom view for browsing, previewing, downloading, and deleting files/directories in default_storage (S3/Local).
    """
    if not request.user.is_staff:
        raise Http404("Permission denied")

    # Default to 'workspaces' folder if path parameter is not explicitly provided
    if 'path' not in request.GET and default_storage.exists('workspaces'):
        current_path = 'workspaces'
    else:
        current_path = request.GET.get('path', '').strip('/')

    action = request.GET.get('action', '')
    target_file = request.GET.get('file', '').strip('/')
    target_dir = request.GET.get('target_dir', '').strip('/')

    base_url = reverse('admin:storage-browser')

    # Detect active Storage Backend
    storage_engine_name = default_storage.__class__.__name__
    if hasattr(default_storage, 'bucket_name'):
        storage_badge = f'<span style="background-color: #238636; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">☁️ AWS S3 Bucket ({escape(str(default_storage.bucket_name))})</span>'
    elif hasattr(default_storage, 'location'):
        storage_badge = f'<span style="background-color: #0d6efd; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">💻 Local FileSystem ({escape(str(default_storage.location))})</span>'
    else:
        storage_badge = f'<span style="background-color: #6e7681; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">📦 Storage: {escape(storage_engine_name)}</span>'

    # 1. Handle File Download
    if action == 'download' and target_file:
        if not default_storage.exists(target_file):
            messages.error(request, f"File '{target_file}' does not exist.")
            return HttpResponseRedirect(f"{base_url}?path={current_path}")
        try:
            file_obj = default_storage.open(target_file, 'rb')
            filename = os.path.basename(target_file)
            mime_type, _ = mimetypes.guess_type(target_file)
            response = FileResponse(file_obj, content_type=mime_type or 'application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            messages.error(request, f"Failed to download file: {str(e)}")
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
        for d in sorted(raw_dirs):
            d_rel_path = os.path.join(current_path, d) if current_path else d
            dirs_list.append({
                'name': d,
                'rel_path': d_rel_path
            })
        for f in sorted(raw_files):
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

            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
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
                        <strong>🔍 File Preview:</strong> <code style="color: #58a6ff;">{escape(target_file)}</code> ({_format_size(size)})
                    </div>
                    <div>
                        <a href="{base_url}?path={escape(current_path)}&action=download&file={escape(target_file)}" style="display: inline-block; background-color: #238636; color: #ffffff !important; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; line-height: 1.2; white-space: nowrap; margin-right: 8px;">⬇️ Download</a>
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
            <td style="padding: 10px 12px; color: #6c757d;">-</td>
            <td style="padding: 10px 12px; text-align: right;">
                <a href="{base_url}?path={escape(current_path)}&action=delete_dir&target_dir={escape(d['rel_path'])}" 
                   onclick="return confirm('Are you sure you want to recursively delete directory `{escape(d['name'])}` and ALL its files?');"
                   style="color: #dc3545; font-size: 12px; text-decoration: none; padding: 3px 8px; border: 1px solid #dc3545; border-radius: 4px;">🗑️ Delete Dir</a>
            </td>
        </tr>
        """)

    # List files
    for f in files_list:
        rows_html.append(f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px 12px;">
                {f['icon']} <a href="{base_url}?path={escape(current_path)}&action=preview&file={escape(f['rel_path'])}" style="font-size: 14px; text-decoration: none; color: #212529;">{escape(f['name'])}</a>
            </td>
            <td style="padding: 10px 12px; color: #495057; font-size: 13px;">{f['size_formatted']}</td>
            <td style="padding: 10px 12px; color: #6c757d; font-size: 13px;">{f['mtime_str']}</td>
            <td style="padding: 10px 12px; text-align: right; white-space: nowrap;">
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

    # Render Django Admin page layout
    page_html = f"""
    <!語html>
    <div id="content" class="colM" style="padding: 20px;">
        <div style="margin-bottom: 16px; font-size: 16px; background: #fff; padding: 12px 16px; border-radius: 6px; border: 1px solid #dee2e6; box-shadow: 0 1px 3px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center;">
            <div>📂 <strong>Storage Browser:</strong> {breadcrumb_nav}</div>
            <div>{storage_badge}</div>
        </div>

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

    # Wrap in Django admin site rendering context if available or standard HttpResponse
    return HttpResponse(page_html)
