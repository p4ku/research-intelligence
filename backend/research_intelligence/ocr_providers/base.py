from abc import ABC, abstractmethod

class BaseOCRProvider(ABC):
    @abstractmethod
    def convert(self, file_path: str, title: str = "Extracted Document", output_format: str = "markdown") -> str:
        """
        Extracts structured text from a PDF file path and formats it as either markdown or html.
        """
        pass
