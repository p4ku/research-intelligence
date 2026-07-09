import sys
import json
from pathlib import Path

# Add backend directory to sys.path to resolve imports correctly
project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
sys.path.append(str(backend_path))

from research_intelligence.scrapers.openalex import OpenAlexScraperProvider

# Define tmp directory inside the prototype folder
tmp_dir = Path(__file__).resolve().parent / "tmp"
tmp_dir.mkdir(parents=True, exist_ok=True)

def main():
    query = "agentic AI"
    limit = 3
    
    print("Initializing OpenAlex Scraper...")
    scraper = OpenAlexScraperProvider()
    
    print(f"Searching OpenAlex for query: '{query}' (limit: {limit})...")
    results = scraper.search(query=query, limit=limit)
    
    if not results:
        print("No articles found or error occurred.")
        return
        
    print(f"Found {len(results)} articles. Processing...")
    
    for i, article in enumerate(results):
        hash_id = article["hash_id"]
        title = article["title"]
        authors = article["authors"]
        pdf_url = article["pdf_url"]
        
        safe_hash_id = hash_id.replace("/", "_")
        
        print(f"\n[{i+1}] Processing Article:")
        print(f"    ID:      {hash_id}")
        print(f"    Title:   {title}")
        print(f"    Authors: {authors}")
        print(f"    PDF URL: {pdf_url}")
        
        # Save metadata to JSON
        metadata_file = tmp_dir / f"openalex_{safe_hash_id}_metadata.json"
        try:
            with metadata_file.open("w", encoding="utf-8") as f:
                json.dump(article, f, indent=2, ensure_ascii=False)
            print(f"    ✓ Saved metadata to {metadata_file.name}")
        except Exception as e:
            print(f"    ✗ Failed to save metadata: {str(e)}")
            
        # Download PDF
        if pdf_url:
            pdf_file = tmp_dir / f"openalex_{safe_hash_id}.pdf"
            if not pdf_url.startswith("http"):
                print(f"    ! Skipping invalid PDF URL: {pdf_url}")
                continue
                
            print(f"    Downloading PDF...")
            try:
                pdf_bytes = scraper.download_file(pdf_url)
                with pdf_file.open("wb") as f:
                    f.write(pdf_bytes)
                print(f"    ✓ Downloaded PDF to {pdf_file.name} ({len(pdf_bytes)} bytes)")
            except Exception as e:
                print(f"    ✗ Failed to download PDF: {str(e)}")
        else:
            print("    ! No PDF URL available for this article.")

if __name__ == "__main__":
    main()
