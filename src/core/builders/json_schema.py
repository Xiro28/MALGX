import re

from src.core.predicate.predicate_container import PredicateContainer
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Union, get_origin, get_args
import json

class JSONSchemaBuilder:

    PREDICATE_PARSED = {} # This will store the mapping of predicate names to their terms and indices for type hinting

    def __init__(self):
        self.predicate_parsed = JSONSchemaBuilder.PREDICATE_PARSED

    def generate(self, predicate: str, types: list) -> type:
        #print(f"Generating class for predicate: {predicate}")

        data = predicate.split("(")
        class_name = data[0]
        
        # 1. Parse terms/arguments safely
        if "(" in predicate:
            args_part = data[1].replace("\"", "").replace(")", "").replace(" ", "")
            terms = args_part.split(",") if ',' in args_part else [args_part]
        else:
            terms = [] # For predicates like type(layered) or just "type"

        class_dict = {}
        annotations = {}
        
        if types != None:
            types = types.split(" ") if ' ' in types else [types]
        else:
            types = [None] * len(terms) # Create a list of None for type hints if no types provided

        # 2. Build Pydantic fields and annotations
        for i, term in enumerate(terms):
            values = []

            type_hint = Union[int, str, None]

            if types and i < len(types) and types[i] is not None:
                if types[i].strip().lower() == "int":
                    type_hint = int
                elif types[i].strip().lower() == "str":
                    type_hint = str

                
            if "[" in term and "]" in term:
                terms[i] = term.split("[")[0]
                values = term.split("[")[1].split("]")[0].split("|")
                values = [v.strip() for v in values] # Clean up whitespace around values
                annotations[terms[i]] = Literal[*values] if values else type_hint
                class_dict[terms[i]] = Field(default=None) # Default None handles missing values

            elif "$" in term:
                terms[i] = term.split("$")[1] # Update term to remove type hint for now
                if ":" in term:
                    terms[i] = terms[i].split(":")[0] # Remove any additional type hints
                    specific_variable_to_get = term.split(":")[1]
                    
                    if specific_variable_to_get in self.predicate_parsed[terms[i]]:
                        target_index = self.predicate_parsed[terms[i]][specific_variable_to_get]
                        
                        for pred in PredicateContainer.get_predicate_value(terms[i]):
                            # Skip entirely empty predicates
                            if not pred or not pred.strip():
                                continue
                                
                            pred_val = [v.strip() for v in pred.split(",")] # Added strip() to clean up whitespace
                            

                            print(f"{target_index} - {len(pred_val)} - {pred_val} - {pred}")
                            # Protect against IndexError
                            if target_index < len(pred_val):
                                values.append(pred_val[target_index])
                            else:
                                print(f"Warning: Index {target_index} out of bounds for predicate '{pred}'")
                else:
                    values = PredicateContainer.get_predicate_value(terms[i])

                annotations[terms[i]] = Literal[*values] if values else type_hint
                class_dict[terms[i]] = Field(default=None) # Default None handles missing values
            else:
                annotations[term] = type_hint
                class_dict[term] = Field(default=None) # Default None handles missing values

        # 3. Method to convert object to ASP fact string: predicate(val1, val2).
        def str_method(self):
            values = [re.sub(r'[^a-zA-Z0-9_]+', lambda m: '_' if '-' in m.group() or '_' in m.group() or m.group().isspace() else '', str(v)).strip('_') for v in self.dict().values() if v is not None]
            if not values and terms: # Avoid printing incomplete atoms
                print("Warning: No values provided for terms, returning empty string to avoid incomplete atom.")
                return ""
            args_str = ", ".join(str(v) for v in values)
            asp_enc =  f"{class_name}({args_str}).".lower() if values else f"{class_name}.".lower()
            return asp_enc

        class_dict['__annotations__'] = annotations
        class_dict['__name__'] = class_name
        class_dict['__str__'] = str_method

        self.predicate_parsed[class_name] = {f"{term}":idx for idx, term in enumerate(class_dict.keys())}

        #print(f"Generated class '{self.predicate_parsed}'")
        
        # Create the 'Atom' class (e.g., in_layer)
        new_class = type(class_name, (BaseModel,), class_dict)

        # 4. Method for the List wrapper to join all facts with spaces
        def list_str_method(self):
            atom_list = getattr(self, f"list_{class_name}", [])
            return " ".join([str(atom) for atom in atom_list if atom])

        # 5. THE KEY CHANGE: Define the schema entry for this predicate
        # This creates the {"layer": "any", "node": "any"} structure
        example_obj = {term: "any" for term in terms} if terms else "null"

        return type(
            f"list_{class_name}",
            (BaseModel,),
            {
                "__name__": f"{class_name}_list",
                "__annotations__": {f"list_{class_name}": List[Optional[new_class]]},
                "__class_params__": terms,
                "__str__": list_str_method,
                # Store the info as a raw dictionary (generate_single_grammar will JSONify it later)
                "__info__": {f"list_{class_name}": [example_obj] if terms else []}
            },
        )

    def generate_single_grammar(self, predicates: list, enable_types: bool = False) -> type:
        self.__classes = []

        # 1. Generate the individual atom/list classes
        for predicate in predicates:
            self.__classes.append(self.generate(predicate))

        class_dict = {}
        annotations = {}
        
        # 2. Build the wrapper fields (e.g., wrapper_in_layer_list)
        for cls in self.__classes:
            # cls.__name__ is e.g., "in_layer_list"
            field_name = f"wrapper_{cls.__name__}"
            class_dict[field_name] = Field(default=None)
            annotations[field_name] = Optional[cls]

        class_dict['__annotations__'] = annotations
        
        # 3. ASP Fact string representation logic
        def str_method(self):
            asp_facts = []
            for _, wrapper_obj in self:
                if wrapper_obj is not None:
                    # str(wrapper_obj) calls list_str_method defined in generate()
                    fact_str = str(wrapper_obj)
                    if fact_str:
                        asp_facts.append(fact_str)
            return "\n".join(asp_facts)
        
        class_dict['__str__'] = str_method

        # 4. THE FIX: Build the JSON Schema for the LLM Prompt
        # This creates a single dictionary containing all predicate structures
        schema_map = {}
        for list_cls in self.__classes:
            # list_cls.__info__ is a dict: {"list_name": [{"arg": "any"}]}
            schema_map.update(list_cls.__info__)
        
        # json.dumps ensures double quotes and valid JSON syntax
        # Using indent=2 makes the prompt much easier for the AI to read
        class_info = json.dumps(schema_map, indent=2)

        class_dict['__info__'] = class_info
            
        # Create the final root wrapper class
        _type = type(
            "predicate_wrapper",
            (BaseModel,),
            class_dict
        )

        return _type

    def get_classes(self) -> tuple:
        return (self.__classes, None)

