from .base import BaseOCRProvider
from .pypdf_provider import PyPDFOCRProvider
from .mistral_provider import MistralOCRProvider


def get_ocr_provider(provider_name: str) -> BaseOCRProvider:
    """
    Returns an instance of the configured OCR provider.
    """
    provider_map = {
        "pypdf": PyPDFOCRProvider,
        "mistral": MistralOCRProvider,
    }
    
    provider_class = provider_map.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown OCR provider: {provider_name}")
        
    return provider_class()
