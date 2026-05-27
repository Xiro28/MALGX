import re
import json
import logging

from time       import time
from random     import randint
from typeguard  import typechecked

from dumbo_asp.primitives.models                import Model

from src.utils.statistics                       import Statistics

from src.core.builders.json_schema              import JSONSchemaBuilder

from src.core.predicate.predicate_container     import PredicateContainer
from src.core.predicate.condition_cache         import ConditionCache
from src.core.predicate.predicate_condition     import predicate_condition


@typechecked
class Predicate:

    def init_predicate(self, config: dict | str):
        self._kb = ""
        self._prompt = ""
        self._condition_info = {"condition": "", "monotone": False}
        self.complex_condition = False
        self.has_set_condition = False
        self.condition_set = None
        self.types = None

        self.rag_text = ""

        if isinstance(config, str):
            logging.info("Simple predicate detected:", config)
            self._prompt = config
            return

        if self.advanced_prompt_type:

            self._prompt = config.get("prompt", "")
            self._kb = config.get("knowledge_base", "")

            if config.get("rag", None) is not None:
                with open(config["rag"], "r") as f:
                    self.rag_text = f.read()

            if config.get("types", None) is not None:
                self.types = config["types"]
            
            cond = config.get("extraction_condition")
            if cond:
                logging.info("Extraction condition detected for predicate", self.defined_predicate, ":", cond)
                if isinstance(cond, list):
                    self._condition_info["condition"] = [predicate_condition(c.get("condition", ""), c.get("monotone", False)) for c in cond]
        else:
            if self.is_predicate_group:
                self._prompt = config.get("prompt", "")
            else:
                if "prompt" in config:
                    # direct prompt key
                    # - predicate: {prompt: ...}
                    self._prompt = config["prompt"]
                else:
                    # default prompt key is the predicate itself
                    # - predicate: prompt -> {predicate: prompt}

                    if isinstance(config, str):
                        self._prompt = config
                    else:
                        self._prompt = config.get(self.defined_predicate, "") 


    def __init__(self, predicate_definition, strings):

        # if "predicates" in predicate_definition:
        #     self.is_predicate_group = True
        #     self.predicate_group = predicate_definition["predicates"]   
        #     self.defined_predicate = " ".join(self.predicate_group)

        #     self.has_predicate_link = False

        #     self.grammar = JSONSchemaBuilder().generate_single_grammar(self.predicate_group)
        # else:
        self.is_predicate_group = False
        self.defined_predicate = next(iter(predicate_definition))
        self.has_predicate_link = "$" in self.defined_predicate
        predicate_definition = predicate_definition[self.defined_predicate]

        if self.has_predicate_link:
                logging.info("Predicate link detected for predicate. Grammar will be lazy updated before each LLM call", self.defined_predicate)



        self.advanced_prompt_type = "extraction_condition" in predicate_definition or "knowledge_base" in predicate_definition

        self.init_predicate(predicate_definition)
        self.grammar = JSONSchemaBuilder().generate(self.defined_predicate, self.types)

        self.formatted_predicate = json.dumps(self.grammar.__info__)
        self.contains_mustache = "{{{" in self._prompt and "}}}" in self._prompt
            
        # Check if the prompt needs string replacements
        if strings:
            replacements = {k: v for d in strings for k, v in d.items()}
            prompt_tokens = re.findall(r"\{([A-Za-z0-9\_]+)\}", self._prompt)
            
            for token in prompt_tokens:
                if token in replacements:
                    self._prompt = self._prompt.replace(f"{{{token}}}", str(replacements[token]))

        # Check wheter a condition is simple (a(1), b(2), ...) or complex (condition_1 :- a(1), condition_2(3) ... condition_3 :- ...)
        # If try goes through the except it means that the condition is complex
        raw_cond = self._condition_info["condition"]

        if raw_cond:
            try:
                # if ConditionCache.get_dependecy_tree_cache() and isinstance(raw_cond, str) and raw_cond:
                #     conditions = calculate_condition_dependency_tree(raw_cond)
                # else:
                conditions = raw_cond

                logging.info("Conditions for predicate", self.defined_predicate, ":", conditions)
                
                self.has_set_condition = isinstance(conditions, list)
                self.condition_set = conditions if self.has_set_condition else None
                
                min_program = self._generate_min_program(conditions)
                Model.of_program(min_program, "", sort=False)

                logging.info("Minimal program for predicate", self.defined_predicate, ":", min_program)
                
                self._condition_info["condition"] = conditions

                self._condition_info["program"] = min_program
                self.complex_condition = False
                
            except Exception:
                logging.info("Complex condition detected for predicate", self.defined_predicate)
                logging.info("Raw condition:", raw_cond)
                self._condition_info["program"] = raw_cond.condition()
                self.complex_condition = True
                self.has_set_condition = False


    def _generate_min_program(self, condition: predicate_condition | list[predicate_condition]) -> str:
        if not condition:
            return ""

        uuid8 = f"uuid{randint(1000, 9999)}"

        if isinstance(condition, list):
            parts = [f"{uuid8}_{i} :- {c.condition()}.\n#show {uuid8}_{i}/0." for i, c in enumerate(condition)]
            return "\n".join(parts)
        
        return f"{uuid8} :- {condition.condition().strip().rstrip('.')}.\n#show {uuid8}/0."

    def evaluate_program(self, conditions: predicate_condition | list[predicate_condition], result: str) -> bool:
        has_model = True
        if self.has_set_condition:
            for idx, cond in enumerate(self.condition_set):
                check = f"_{idx}" in result
                has_model = has_model and check
                ConditionCache.update(cond, check)
        else:
            has_model = len(result) > 0
            ConditionCache.update(conditions, has_model)

        return has_model

    def execute_condition(self, program: str, conditions: predicate_condition | list[predicate_condition]) -> bool:
        if not program.strip():
            return False

        try:
            start_time = time()
            model = Model.of_program(program, PredicateContainer.get_all_predicates(), sort=False)
            Statistics.log_solver_call()
            Statistics.log_asp_solver_time(time() - start_time)
            has_model = self.evaluate_program(conditions, model.as_facts)
            return has_model
        except Exception:
            logging.error(f"Error during inference. {self.defined_predicate}", exc_info=True)
            return False

    def has_to_be_extracted(self):
        cond = self._condition_info.get("condition", "")
        if not self.advanced_prompt_type or not cond:
            return True

        if ConditionCache.canSkipSolver(cond, self.complex_condition):
            return ConditionCache.get(cond)
        
        return self.execute_condition(self._condition_info["program"], cond)
        
    def run_kb(self, extracted_facts=""):
        if self.advanced_prompt_type and self._kb:
            try:
                full_program = f"{PredicateContainer.get_all_predicates()} {extracted_facts}"
                return Model.of_program(self._kb, full_program, sort=False).as_facts
            except Exception as e:
                pass

        return extracted_facts
    
    def get_grammar(self) -> type:
        if self.has_predicate_link:
            self.grammar = JSONSchemaBuilder().generate(self.defined_predicate, self.types)
        return self.grammar
    
    def parse_response(self, response) -> list[str]:
        return str(response).splitlines()

    @property
    def prompt_description(self):
        if self.contains_mustache:
            #get the predicate inside the mustache and replace it with the value of the predicate
            mustaches = re.findall(r"\{{3}([A-Za-z0-9\_]+)\}{3}", self._prompt) 
            new_prompt = self._prompt
            for predicate_name in mustaches:
                predicate_value = PredicateContainer.get_predicate_value(predicate_name)
                target_string = "{{{" + predicate_name + "}}}"
                if isinstance(predicate_value, list):
                    replacement_str = " and ".join("\'" + str(item) + "\'" for item in predicate_value)
                else:
                    replacement_str = str(predicate_value)
                new_prompt = new_prompt.replace(target_string, replacement_str)
            return new_prompt
        
        return self._prompt

    @property
    def predicate(self):
        return self.defined_predicate
    
    @property
    def predicate_formatted(self):
        return str(self.formatted_predicate)
    
    @property
    def rag_description(self):
        return self.rag_text
    
    def __str__(self):
        return self.defined_predicate
