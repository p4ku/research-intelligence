import base64
import json
import logging
import mimetypes
import os
import re
import uuid
from typing import Any
from urllib.parse import quote

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import models
from django.http import HttpResponse, FileResponse, HttpResponseRedirect, Http404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin

logger = logging.getLogger(__name__)


@method_decorator(xframe_options_sameorigin, name='dispatch')
class StorageBrowserView(View):
    """
    Encapsulated Django Admin Class-Based View for browsing, inspecting,
    previewing, downloading, and managing storage files and virtual prefixes
    across AWS S3 / MinIO and local file systems.
    """
    storage = default_storage

    def dispatch(self, request, *args, **kwargs):
        # Admin authentication and staff permission check
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, "Staff permission required to access Storage Browser.")
            return HttpResponseRedirect(reverse('admin:login'))
        return super().dispatch(request, *args, **kwargs)

    # -------------------------------------------------------------------------
    # 1. Static Utilities & Security Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def sanitize_filename(name: str, max_length: int = 120) -> str:
        """Sanitizes a string to be used safely as a downloaded filename across operating systems."""
        clean = re.sub(r'[\\/*?:"<>|]', '', name)
        clean = re.sub(r'\s+', '_', clean.strip())
        clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '', clean)
        clean = clean.strip('._-')
        if len(clean) > max_length:
            clean = clean[:max_length].rstrip('._-')
        return clean or "document"

    @staticmethod
    def get_file_icon(filename: str) -> str:
        """Returns visual emoji badge representing file type."""
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

    @staticmethod
    def format_size(size_bytes: int | None) -> str:
        """Formats byte sizes into human-readable representation."""
        if size_bytes is None:
            return "-"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    @classmethod
    def is_allowed_path(cls, path: str) -> bool:
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

    @classmethod
    def resolve_friendly_filename(cls, target_file: str) -> str:
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
                    prefix = f"{cls.sanitize_filename(doc.arxiv_id)}_"
            elif paper:
                title = paper.title
                if paper.arxiv_id:
                    prefix = f"{cls.sanitize_filename(paper.arxiv_id)}_"

            if title:
                safe_title = cls.sanitize_filename(title)
                suffix = f"_{base_stem}" if base_stem.startswith('ocr_') else ""
                return f"{prefix}{safe_title}{suffix}{ext}"
        except Exception as e:
            logger.warning(f"Failed to resolve friendly filename for '{target_file}': {e}")

        return default_name

    @classmethod
    def recursive_delete_dir(cls, dir_path: str, storage: Any = default_storage) -> int:
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
        if hasattr(storage, 'bucket') and storage.bucket is not None:
            try:
                prefix = clean_dir if clean_dir.endswith('/') else f"{clean_dir}/"
                objects_to_delete = storage.bucket.objects.filter(Prefix=prefix)
                for obj in objects_to_delete:
                    obj.delete()
                    deleted_count += 1
                try:
                    storage.bucket.objects.filter(Prefix=clean_dir).delete()
                except Exception:
                    pass
                return deleted_count
            except Exception as s3_err:
                logger.warning(f"S3 bucket prefix delete failed for '{clean_dir}': {s3_err}")

        # 2. Standard recursive listdir deletion
        try:
            dirs, files = storage.listdir(clean_dir)
            for f in files:
                full_f_path = f"{clean_dir}/{f}"
                try:
                    if storage.exists(full_f_path):
                        storage.delete(full_f_path)
                        deleted_count += 1
                except Exception:
                    pass
            for d in dirs:
                full_d_path = f"{clean_dir}/{d}"
                deleted_count += cls.recursive_delete_dir(full_d_path, storage=storage)
        except Exception as list_err:
            logger.warning(f"Storage listdir error during recursive delete of '{clean_dir}': {list_err}")

        # 3. Local filesystem cleanup: physically remove empty folder or folder tree from disk
        local_path = None
        if hasattr(storage, 'path'):
            try:
                local_path = storage.path(clean_dir)
            except Exception:
                pass
        if not local_path and hasattr(storage, 'location'):
            try:
                local_path = os.path.join(storage.location, clean_dir)
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

        # 4. Also attempt storage.delete on the directory name and with trailing slash
        for candidate in (clean_dir, f"{clean_dir}/"):
            try:
                if storage.exists(candidate):
                    storage.delete(candidate)
            except Exception:
                pass

        return deleted_count

    # -------------------------------------------------------------------------
    # 2. Metadata & Directory Listing
    # -------------------------------------------------------------------------
    def get_storage_badge(self) -> str:
        """Renders visual storage engine badge for the admin interface."""
        storage_backend = type(self.storage).__name__
        if "S3" in storage_backend:
            bucket_name = getattr(self.storage, 'bucket_name', 'AWS S3')
            endpoint = os.environ.get('AWS_S3_ENDPOINT_URL', '')
            label = f"MinIO ({bucket_name})" if "localhost" in endpoint or "127.0.0.1" in endpoint or "minio" in endpoint else f"AWS S3 ({bucket_name})"
            return f'<span style="background-color: #ffc107; color: #000; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">☁️ {escape(label)}</span>'
        else:
            loc = getattr(self.storage, 'location', 'Local Disk')
            return f'<span style="background-color: #0d6efd; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">💻 Local FileSystem ({escape(str(loc))})</span>'

    def resolve_folder_metadata(self, folder_name: str, folder_rel_path: str) -> dict:
        """
        Resolves mtime and friendly name/title for virtual directories and hashes.
        """
        d_mtime_str = "-"
        doc_title = None
        ws_name = None

        try:
            d_mtime = self.storage.get_modified_time(folder_rel_path)
            d_mtime_str = d_mtime.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        # Fallback for S3/MinIO virtual prefixes where directories have no direct filesystem metadata:
        # If folder name is a valid UUID, look up matching Workspace or PipelineRun
        # If folder name is a 64-character hex hash, look up DocumentRegistry or Paper title & timestamp
        try:
            if len(folder_name) == 36:
                if uuid.UUID(folder_name):
                    from research_intelligence.models import Workspace, PipelineRun
                    ws = Workspace.objects.filter(id=folder_name).only('name', 'created_at').first()
                    if ws:
                        ws_name = ws.name
                        if d_mtime_str == "-" and ws.created_at:
                            d_mtime_str = ws.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        pr = PipelineRun.objects.filter(id=folder_name).only('created_at').first()
                        if pr and pr.created_at:
                            if d_mtime_str == "-":
                                d_mtime_str = pr.created_at.strftime("%Y-%m-%d %H:%M:%S")
            elif len(folder_name) == 64:
                from research_intelligence.models import DocumentRegistry, Paper
                doc = DocumentRegistry.objects.filter(sha256_hash=folder_name).only('title', 'first_ingested_at').first()
                if doc:
                    doc_title = doc.title
                    if d_mtime_str == "-" and doc.first_ingested_at:
                        d_mtime_str = doc.first_ingested_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    p = Paper.objects.filter(sha256_hash=folder_name).only('title', 'created_at').first()
                    if p:
                        doc_title = p.title
                        if d_mtime_str == "-" and p.created_at:
                            d_mtime_str = p.created_at.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        return {
            'name': folder_name,
            'rel_path': folder_rel_path,
            'mtime_str': d_mtime_str,
            'doc_title': doc_title,
            'ws_name': ws_name,
        }

    def list_directory(self, current_path: str, sort_by: str, sort_order: str) -> tuple[list[dict], list[dict]]:
        """
        Lists and sorts subdirectories and files within current_path.
        """
        dirs_list = []
        files_list = []

        raw_dirs, raw_files = self.storage.listdir(current_path)

        # When browsing root (/), strictly filter to allowed storage roots (workspaces, cache, test folders)
        if not current_path:
            filtered_dirs = [d for d in raw_dirs if d in ('workspaces', 'cache') or d.startswith('test_')]
            if 'workspaces' not in filtered_dirs and (self.storage.exists('workspaces') or not filtered_dirs):
                filtered_dirs.append('workspaces')
            if 'cache' not in filtered_dirs and (self.storage.exists('cache') or self.storage.exists('cache/documents') or not filtered_dirs):
                filtered_dirs.append('cache')
            filtered_files = []
        elif current_path == 'cache':
            filtered_dirs = [d for d in raw_dirs]
            if 'documents' not in filtered_dirs and (self.storage.exists('cache/documents') or not filtered_dirs):
                filtered_dirs.append('documents')
            filtered_files = raw_files
        else:
            filtered_dirs = raw_dirs
            filtered_files = raw_files

        # Enumerate directories with metadata
        for d in filtered_dirs:
            d_rel_path = os.path.join(current_path, d) if current_path else d
            meta = self.resolve_folder_metadata(d, d_rel_path)
            dirs_list.append(meta)

        # Enumerate files with metadata
        for f in filtered_files:
            f_rel_path = os.path.join(current_path, f) if current_path else f
            size = None
            mtime_str = "-"
            try:
                size = self.storage.size(f_rel_path)
            except Exception:
                pass
            try:
                mtime = self.storage.get_modified_time(f_rel_path)
                mtime_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

            files_list.append({
                'name': f,
                'rel_path': f_rel_path,
                'icon': self.get_file_icon(f),
                'size_bytes': size or 0,
                'size_formatted': self.format_size(size),
                'mtime_str': mtime_str
            })

        # Apply sorting
        is_desc = (sort_order == 'desc')
        if sort_by == 'mtime':
            dirs_list.sort(key=lambda x: (x['mtime_str'] if x['mtime_str'] != '-' else '0000-00-00 00:00:00', x['name']), reverse=is_desc)
            files_list.sort(key=lambda x: (x['mtime_str'] if x['mtime_str'] != '-' else '0000-00-00 00:00:00', x['name']), reverse=is_desc)
        elif sort_by == 'size':
            dirs_list.sort(key=lambda x: x['name'].lower(), reverse=is_desc)
            files_list.sort(key=lambda x: x.get('size_bytes', 0) or 0, reverse=is_desc)
        else:  # sort_by == 'name'
            dirs_list.sort(key=lambda x: x['name'].lower(), reverse=is_desc)
            files_list.sort(key=lambda x: x['name'].lower(), reverse=is_desc)

        return dirs_list, files_list

    # -------------------------------------------------------------------------
    # 3. Action Handlers (View Raw, Download, Delete, Preview)
    # -------------------------------------------------------------------------
    def handle_view_raw(self, request, target_file: str) -> HttpResponse:
        """Handles inline raw streaming for PDF and media files in a new tab or iframe."""
        if not self.storage.exists(target_file):
            raise Http404("File not found.")
        try:
            f = self.storage.open(target_file, 'rb')
            ext = os.path.splitext(target_file)[1].lower()
            mime_type, _ = mimetypes.guess_type(target_file)
            content_type = 'application/pdf' if ext == '.pdf' else (mime_type or 'application/octet-stream')

            response = FileResponse(f, content_type=content_type)
            friendly_name = self.resolve_friendly_filename(target_file)
            encoded_name = quote(friendly_name)
            response['Content-Disposition'] = f'inline; filename="{friendly_name}"; filename*=UTF-8\'\'{encoded_name}'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            return response
        except Exception as e:
            logger.error(f"Error opening raw file '{target_file}': {e}")
            raise Http404("Could not read file.")

    def handle_download(self, request, target_file: str) -> HttpResponse:
        """Handles file download with RFC 5987 friendly filenames."""
        if not self.storage.exists(target_file):
            raise Http404("File not found.")
        try:
            f = self.storage.open(target_file, 'rb')
            friendly_name = self.resolve_friendly_filename(target_file)
            encoded_name = quote(friendly_name)
            mime_type, _ = mimetypes.guess_type(friendly_name)

            response = FileResponse(f, as_attachment=True, filename=friendly_name, content_type=mime_type or 'application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{friendly_name}"; filename*=UTF-8\'\'{encoded_name}'
            return response
        except Exception as e:
            logger.error(f"Error downloading file '{target_file}': {e}")
            raise Http404("Could not read file.")

    def handle_delete_file(self, request, target_file: str, current_path: str, base_url: str) -> HttpResponseRedirect:
        """Handles individual file deletion."""
        try:
            if self.storage.exists(target_file):
                self.storage.delete(target_file)
                messages.success(request, f"File '{target_file}' was successfully deleted.")
            else:
                messages.warning(request, f"File '{target_file}' does not exist.")
        except Exception as e:
            messages.error(request, f"Error deleting file '{target_file}': {str(e)}")
        return HttpResponseRedirect(f"{base_url}?path={current_path}")

    def handle_delete_dir(self, request, target_dir: str, current_path: str, base_url: str) -> HttpResponseRedirect:
        """Handles recursive directory deletion."""
        try:
            deleted_count = self.recursive_delete_dir(target_dir, storage=self.storage)
            messages.success(request, f"Directory '{target_dir}' and {deleted_count} file(s) were successfully deleted.")
        except Exception as e:
            messages.error(request, f"Error deleting directory '{target_dir}': {str(e)}")
        return HttpResponseRedirect(f"{base_url}?path={current_path}")

    # -------------------------------------------------------------------------
    # 4. HTML Renderers
    # -------------------------------------------------------------------------
    def render_breadcrumbs(self, current_path: str, base_url: str) -> str:
        """Builds interactive breadcrumbs navigation."""
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
        return " / ".join(breadcrumb_html)

    def render_preview_box(self, request, target_file: str, current_path: str, base_url: str) -> str:
        """Renders file preview box for JSON, text, Markdown, images, and embedded PDF iframes."""
        if not target_file or not self.storage.exists(target_file):
            return ""

        try:
            size = self.storage.size(target_file)
            ext = os.path.splitext(target_file)[1].lower()
            mime_type, _ = mimetypes.guess_type(target_file)
            friendly_name = self.resolve_friendly_filename(target_file)
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
                f_bytes = self.storage.open(target_file, 'rb').read()
                b64_str = base64.b64encode(f_bytes).decode('utf-8')
                mime = mime_type or 'image/png'
                preview_body = f'<div style="text-align: center; padding: 20px;"><img src="data:{mime};base64,{b64_str}" style="max-width: 100%; max-height: 500px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);" /></div>'
            elif size and size > 1024 * 1024:
                preview_body = f'<div style="padding: 20px; color: #888;">File is too large for inline preview ({self.format_size(size)}). Use the download button below.</div>'
            else:
                f_bytes = self.storage.open(target_file, 'rb').read(1024 * 1024)
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

            return f"""
            <div style="margin: 20px 0; border: 1px solid #30363d; border-radius: 6px; overflow: hidden; background-color: #161b22; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                <div style="padding: 10px 16px; background-color: #21262d; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; color: #f0f6fc;">
                    <div>
                        <strong>🔍 File Preview:</strong> <code style="color: #58a6ff;">{escape(target_file)}</code> ({self.format_size(size)}){friendly_display}
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
            return f'<div class="errornote">Error generating preview: {escape(str(e))}</div>'

    def render_table(self, dirs_list: list[dict], files_list: list[dict], current_path: str, base_url: str, sort_by: str, sort_order: str) -> str:
        """Renders the HTML table rows and sortable column headers."""
        rows_html = []

        # Parent directory navigation
        if current_path:
            parent_path = '/'.join(current_path.split('/')[:-1])
            rows_html.append(f"""
            <tr>
                <td colspan="4" style="padding: 10px 12px; background-color: #f8f9fa;">
                    📁 <a href="{base_url}?path={escape(parent_path)}" style="font-weight: bold; text-decoration: none;">.. (Parent Directory)</a>
                </td>
            </tr>
            """)

        # Subdirectory rows
        for d in dirs_list:
            doc_title_span = ""
            if d.get('doc_title'):
                doc_title_span = f'<span style="color: #495057; font-size: 13px; font-weight: normal; margin-left: 8px;">— <strong>{escape(d["doc_title"])}</strong></span>'
            elif d.get('ws_name'):
                doc_title_span = f'<span style="color: #495057; font-size: 13px; font-weight: normal; margin-left: 8px;">— <strong>{escape(d["ws_name"])}</strong></span>'

            rows_html.append(f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px 12px;">
                    📁 <a href="{base_url}?path={escape(d['rel_path'])}" style="font-weight: bold; font-size: 14px; text-decoration: none; color: #0d6efd;">{escape(d['name'])}/</a>
                    {doc_title_span}
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

        # File rows
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

        return "\n".join(rows_html)

    # -------------------------------------------------------------------------
    # 5. Main View Dispatcher (GET)
    # -------------------------------------------------------------------------
    def get(self, request, *args, **kwargs) -> HttpResponse:
        base_url = reverse('admin:storage-browser')
        current_path = request.GET.get('path', '').strip('/')
        action = request.GET.get('action', '')
        target_file = request.GET.get('file', '').strip('/')
        target_dir = request.GET.get('target_dir', '').strip('/')

        # 1. Validate security paths
        for candidate in (current_path, target_file, target_dir):
            if candidate and not self.is_allowed_path(candidate):
                messages.error(request, f"Access denied: path '{candidate}' is outside the authorized storage boundary.")
                return HttpResponseRedirect(base_url)

        # 2. Dispatch dedicated action handlers
        if action == 'view_raw' and target_file:
            return self.handle_view_raw(request, target_file)

        if action == 'download' and target_file:
            return self.handle_download(request, target_file)

        if action == 'delete_file' and target_file:
            return self.handle_delete_file(request, target_file, current_path, base_url)

        if action == 'delete_dir' and target_dir:
            return self.handle_delete_dir(request, target_dir, current_path, base_url)

        # 3. Determine sorting preference
        default_sort_by = 'mtime' if (current_path.startswith('cache/documents') or '/runs' in current_path or current_path.endswith('/documents')) else 'name'
        default_sort_order = 'desc' if default_sort_by == 'mtime' else 'asc'

        sort_by = request.GET.get('sort', default_sort_by)
        sort_order = request.GET.get('order', default_sort_order).lower()
        if sort_order not in ('asc', 'desc'):
            sort_order = default_sort_order

        # 4. List directory contents
        dirs_list, files_list = [], []
        try:
            dirs_list, files_list = self.list_directory(current_path, sort_by, sort_order)
        except Exception as e:
            messages.error(request, f"Error listing path '{current_path}': {str(e)}")

        # 5. Build HTML components
        breadcrumb_nav = self.render_breadcrumbs(current_path, base_url)
        preview_box_html = self.render_preview_box(request, target_file, current_path, base_url) if action == 'preview' else ""
        table_body = self.render_table(dirs_list, files_list, current_path, base_url, sort_by, sort_order)
        storage_badge = self.get_storage_badge()

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

        # Helper for building sort links in table headers
        def _sort_link(col_name: str, col_label: str) -> str:
            if sort_by == col_name:
                next_order = 'asc' if sort_order == 'desc' else 'desc'
                arrow = ' 🔽' if sort_order == 'desc' else ' 🔼'
                return f'<a href="{base_url}?path={escape(current_path)}&sort={col_name}&order={next_order}" style="color: #0d6efd; text-decoration: none; font-weight: bold;">{col_label}{arrow}</a>'
            return f'<a href="{base_url}?path={escape(current_path)}&sort={col_name}&order=desc" style="color: #495057; text-decoration: none;">{col_label}</a>'

        # Render Full Admin Page
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
                            <th style="padding: 12px;">{_sort_link('name', 'Name')}</th>
                            <th style="padding: 12px; width: 120px;">{_sort_link('size', 'Size')}</th>
                            <th style="padding: 12px; width: 220px;">{_sort_link('mtime', 'Modified / Created')}</th>
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


# -----------------------------------------------------------------------------
# Module-level aliases & view entrypoint (for 100% backward compatibility)
# -----------------------------------------------------------------------------
storage_browser_view = StorageBrowserView.as_view()

_sanitize_filename = StorageBrowserView.sanitize_filename
_get_file_icon = StorageBrowserView.get_file_icon
_format_size = StorageBrowserView.format_size
_is_allowed_path = StorageBrowserView.is_allowed_path
_resolve_friendly_filename = StorageBrowserView.resolve_friendly_filename
_recursive_delete_dir = StorageBrowserView.recursive_delete_dir
