import re
import logging

from typing         import Optional
from dataclasses    import dataclass, field

from src.core.predicate.predicate             import Predicate
from src.core.llm_handler                     import LLMHandler
from src.core.predicate.predicate_container   import PredicateContainer

_LEADING_ZERO_INT = re.compile(r"\b0+(\d+)\b")
def _strip_leading_zeros_in_int_tokens(s: str) -> str:
    def repl(m: re.Match) -> str:
        return str(int(m.group(1)))
    return _LEADING_ZERO_INT.sub(r"\1", s)


_BAD_START = re.compile(r"\b(\d+[A-Za-z_][A-Za-z0-9_]*)\b")
def prefix_fix(s: str) -> str:
    return _BAD_START.sub(r"malformed_term_failure__\1", s)

@dataclass()
class EvaluatePrompt:
    llm_model:          str
    behaviour_config:   dict
    application_config: dict
    

    __llm_instance:         Optional[LLMHandler]    = field(init=False, default=None)
    __predicates:           list[Predicate]         = field(init=False, default_factory=list)


    def __post_init__(self):
        self.__system_prompt = self.behaviour_config['init']
        
        self.__llm_instance = LLMHandler(self.llm_model, self.__system_prompt)

        # get the costant strings
        self.__strings = self.application_config.get('strings', {})

        if self.__strings is {}:
            logging.warning("Warning: No constant strings provided in application config. Use the 'strings' field to provide them.")
            pass

        # Get all the predicates from the application config
        self.__predicates = [Predicate(pred, self.__strings) for pred in self.application_config.get('extract', [])]

    def __filter_asp_atoms__(self, req: str) -> str:
        req = _strip_leading_zeros_in_int_tokens(req)
        req = prefix_fix(req)
        return " ".join(re.findall(r"\w+(?:\([a-zA-Z0-9_]+(?:,\s*[a-zA-Z0-9_]+)*\))?\.", req))
    

    def __structured_output_call(self, input_text: str, image_path: str | bytes | None = None) -> tuple: # type: ignore
        context = self.application_config.get("context", "")

        behaviour_context = ""
        behaviour_mapping = self.behaviour_config["mapping"].replace("{input}", input_text)

        if context != None:
            behaviour_context = self.behaviour_config["context"].replace("{context}", f"{context}")
        
        for _, predicate in enumerate(self.__predicates):

            if not predicate.has_to_be_extracted():
                continue

            appl_mapping = behaviour_mapping.replace("{instructions}", f"{predicate.prompt_description}\nRAG DATA:\n{predicate.rag_description}")
            appl_mapping = appl_mapping.replace("{atom}", predicate.predicate_formatted)

            if image_path is not None:
                yield self.__llm_instance.invoke_llm_constrained_image(appl_mapping, predicate.get_grammar(), behaviour_context, image_path), predicate
            else:
                yield self.__llm_instance.invoke_llm_constrained(appl_mapping, predicate.get_grammar(), behaviour_context), predicate

        return (None, None)

    def run(self, input_text: str, image: str | bytes | None = None) -> str:
        for response, predicate in self.__structured_output_call(input_text, image):
            if response is None and predicate is None:
                continue
            atom_list = predicate.parse_response(response)
            if atom_list:
                extracted_facts = self.__filter_asp_atoms__(" ".join(atom_list))
                execute_kb = predicate.run_kb(extracted_facts)
                for atom in execute_kb.replace(", ", ",").split(" "):
                    PredicateContainer.add_predicate(atom)
        response = PredicateContainer.get_all_predicates()
        PredicateContainer.reset_container()
        return response
