import sys
import os
import json
from pathlib import Path

# Add backend directory to sys.path to resolve imports and Django modules correctly
project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
sys.path.append(str(backend_path))

# Setup Django environment so that the Lens API key (and other Django settings) can be loaded
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
import django
django.setup()

from research_intelligence.scrapers.arxiv import ArxivScraperProvider
from research_intelligence.scrapers.lens import LensScraperProvider
from research_intelligence.scrapers.openalex import OpenAlexScraperProvider

# Define tmp directory inside the prototype folder
tmp_dir = Path(__file__).resolve().parent / "tmp"
tmp_dir.mkdir(parents=True, exist_ok=True)

def run_scraper(name: str, provider, query: str, limit: int):
    print("=" * 80)
    print(f"RUNNING SCRAPER: {name.upper()}")
    print("=" * 80)
    print(f"Searching for query: '{query}' (limit: {limit})...")
    
    results = provider.search(query=query, limit=limit)
    if not results:
        print(f"No articles found or error occurred with '{name}' scraper.")
        return
        
    print(f"Found {len(results)} articles. Processing...")
    for i, article in enumerate(results):
        hash_id = article["hash_id"]
        title = article["title"]
        authors = article["authors"]
        pdf_url = article["pdf_url"]
        
        # Sanitize hash_id for filename use
        safe_hash_id = f"{name}_{hash_id.replace('/', '_')}"
        
        print(f"\n[{i+1}] Article details:")
        print(f"    ID:      {hash_id}")
        print(f"    Title:   {title}")
        print(f"    Authors: {authors}")
        print(f"    PDF URL: {pdf_url}")
        
        # Save metadata to JSON
        metadata_file = tmp_dir / f"{safe_hash_id}_metadata.json"
        try:
            with metadata_file.open("w", encoding="utf-8") as f:
                json.dump(article, f, indent=2, ensure_ascii=False)
            print(f"    ✓ Saved metadata to {metadata_file.name}")
        except Exception as e:
            print(f"    ✗ Failed to save metadata: {str(e)}")
            
        # Download PDF
        if pdf_url:
            pdf_file = tmp_dir / f"{safe_hash_id}.pdf"
            if not pdf_url.startswith("http"):
                print(f"    ! Skipping invalid PDF URL: {pdf_url}")
                continue
            
            print(f"    Downloading from URL: {pdf_url} ...")
            try:
                pdf_bytes = provider.download_file(pdf_url)
                with pdf_file.open("wb") as f:
                    f.write(pdf_bytes)
                print(f"    ✓ Downloaded PDF to {pdf_file.name} ({len(pdf_bytes)} bytes)")
            except Exception as e:
                print(f"    ✗ Failed to download file: {str(e)}")
        else:
            print("    ! No PDF URL available for this article.")
    print("\n" + "=" * 80 + "\n")

def main():
    query = "agentic AI"
    limit = 2
    
    # Initialize all providers
    providers = {
        "arxiv": ArxivScraperProvider(),
        "openalex": OpenAlexScraperProvider(),
        "lens": LensScraperProvider(),
    }
    
    for name, provider in providers.items():
        try:
            run_scraper(name, provider, query, limit)
        except Exception as e:
            print(f"Error running {name} scraper: {str(e)}")

if __name__ == "__main__":
    main()
