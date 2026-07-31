import os
import importlib

# Automatically import all submodules within research_intelligence.tasks so Celery registers all @shared_task functions
def _import_all_tasks():
    package_dir = os.path.dirname(__file__)
    for root, _, files in os.walk(package_dir):
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, package_dir)
                mod_name = rel_path[:-3].replace(os.sep, '.')
                try:
                    importlib.import_module(f'research_intelligence.tasks.{mod_name}')
                except Exception:
                    pass

_import_all_tasks()
