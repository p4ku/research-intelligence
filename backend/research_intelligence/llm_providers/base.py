import abc

class BaseLLMProvider(abc.ABC):
    """
    Abstract base class for all pluggable LLM API drivers.
    Defines standard client behaviors and parsing constraints.
    """

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        response_schema: dict = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str = None
    ) -> str:
        """
        Executes a prompt generation.
        Returns the raw model completion string.
        """
        pass
