import re

from src.core.predicate.condition_cache import ConditionCache

class PredicateContainer:
    _predicates = list()

    @staticmethod
    def add_predicate(predicate: str):
        PredicateContainer._predicates.append(predicate)
        #we have to invalidate non-monotone caches because new facts can affect them
        ConditionCache.invalidate(monotone=False)

    @staticmethod
    def remove_predicate(predicate: str):
        PredicateContainer._predicates.remove(predicate)

        #here instead we invalidate both caches because removing a fact can affect both monotone and non-monotone conditions
        ConditionCache.invalidateAll()
        
    @staticmethod
    def get_predicate_value(predicate_head: str) -> list[str]:

        values = []
        # Use regex to find all matches non-greedily. 
        # Example match: robot_command(5, insert) -> extracts "5, insert"
        pattern = re.compile(rf"{re.escape(predicate_head)}\((.*?)\)")

        for pred in PredicateContainer._predicates:
            matches = pattern.findall(pred)
            for match in matches:
                clean_match = match.strip()
                values.append(clean_match)
                
        return values if values else [""]
    
    @staticmethod
    def get_all_values_for_predicate(predicate_head: str) -> str:
        values = ""
        for pred in PredicateContainer._predicates:
            if pred.startswith(predicate_head + "("):
                value = pred.split("(", 1)[1].rsplit(")", 1)[0]  # Extract the value inside the parentheses
                values += value + " "
        values = values.strip()  # Remove trailing space
        return values
    
    @staticmethod
    def reset_container():
        PredicateContainer._predicates = list()
        ConditionCache.clear()

    @staticmethod
    def get_all_predicates():
        return "\n".join(PredicateContainer._predicates)