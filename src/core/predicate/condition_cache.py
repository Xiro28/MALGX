import logging

from src.utils.statistics                   import Statistics
from src.core.predicate.predicate_condition import predicate_condition

class ConditionCache:
    non_monotone_cache = {}
    monotone_cache = {}

    enabled = True
    
    strict = True
    dependecy_tree_graph = False
    mode = "all"  # possible values: "all", "monotone", "non_monotone"

    @staticmethod
    def disable():
        ConditionCache.enabled = False

    @staticmethod
    def enable():
        ConditionCache.enabled = True

    @staticmethod
    def set_only_monotone():
        ConditionCache.mode = "monotone"

    @staticmethod
    def set_only_non_monotone():
        ConditionCache.mode = "non_monotone"
    
    @staticmethod
    def set_all():
        ConditionCache.mode = "all"
    
    @staticmethod
    def set_use_dependecy_tree_cache(flag: bool):
        ConditionCache.dependecy_tree_graph = flag
        ConditionCache.strict = not flag

    @staticmethod
    def get_dependecy_tree_cache():
        return ConditionCache.dependecy_tree_graph
    
    @staticmethod
    def is_strict_cache():
        return ConditionCache.strict

    @staticmethod
    def update(condition : predicate_condition, value : bool):

        if not ConditionCache.enabled:
            return

        if condition.is_monotone() and ConditionCache.mode in ["all", "monotone"]:
            ConditionCache.monotone_cache[condition.condition()] = value
        else:
            ConditionCache.non_monotone_cache[condition.condition()] = value

    @staticmethod
    def canSkipSolver(conditions: list[predicate_condition] | predicate_condition, is_complex: bool = False) -> bool:

        if not ConditionCache.enabled:
            return False
        
        if isinstance(conditions, predicate_condition):
            
            # If it's not complex try to extract the dependecy graph if any
            # if not is_complex and not ConditionCache.strict:
            #     keys = calculate_condition_dependency_tree(keys)

            # # If the dependecy graph has failed to be extracted or it's a complex condition.
            # # Put in array so we can iterate over it
            # if isinstance(keys, str):
            conditions = [conditions]

        canSkip = True

        
        for condition in conditions:
            if condition.condition() == "":
                continue

            # if not condition.is_monotone():
            #     canSkip = False
            #     break

            if condition.condition() in ConditionCache.non_monotone_cache and ConditionCache.mode in ["all", "non_monotone"]:
                Statistics.log_cache_hit_non_monotone()
            elif condition.condition() in ConditionCache.monotone_cache and ConditionCache.mode in ["all", "monotone"]:
                Statistics.log_cache_hit_monotone()
            else:

                if condition.is_monotone():
                    Statistics.log_cache_miss_monotone()
                else:
                    Statistics.log_cache_miss_non_monotone()

                canSkip = False
                break

        if canSkip:
            logging.info(f"Skipped condition: {str(conditions)}\nWith non-monotone cache:\n{ConditionCache.non_monotone_cache}\nMonotone cache:\n{ConditionCache.monotone_cache}\n")
            Statistics.log_cache_solver_skip_counter()

        return canSkip

    @staticmethod
    def invalidate(monotone: bool = False):
        if monotone and ConditionCache.mode in ["all", "monotone"]:
            ConditionCache.monotone_cache = {}
            Statistics.log_monotone_cache_invalidation()
        else:
            ConditionCache.non_monotone_cache = {}
            Statistics.log_non_monotone_cache_invalidation()

        logging.info(f"Invalidated {'monotone' if monotone else 'non-monotone'} cache. Current state:\nNon-monotone cache:\n{ConditionCache.non_monotone_cache}\nMonotone cache:\n{ConditionCache.monotone_cache}\n")

    @staticmethod
    def invalidateAll():
        logging.info("Invalidating all caches.")
        ConditionCache.invalidate(monotone=True)
        ConditionCache.invalidate(monotone=False)

    @staticmethod
    def reset():
        ConditionCache.non_monotone_cache = {}
        ConditionCache.monotone_cache = {}
        ConditionCache.mode = "all"

    @staticmethod
    def clear():
        ConditionCache.non_monotone_cache = {}
        ConditionCache.monotone_cache = {}

    @staticmethod
    def get(conditions: predicate_condition | list[predicate_condition]) -> bool:

        if not ConditionCache.enabled:
            return False

        if isinstance(conditions, predicate_condition):
            if conditions.is_monotone() and ConditionCache.mode in ["all", "monotone"]:
                return ConditionCache.monotone_cache.get(conditions.condition(), False)
            elif not conditions.is_monotone() and ConditionCache.mode in ["all", "non_monotone"]:
                return ConditionCache.non_monotone_cache.get(conditions.condition(), False)
            else:
                logging.error("ConditionCache: Unable to get condition from cache due to mode mismatch.")
                return False
        elif isinstance(conditions, list):
            res = True
            for condition in conditions:
                if condition == "":
                    continue

                if not condition.is_monotone() and ConditionCache.mode in ["all", "non_monotone"]:
                    res = res and ConditionCache.non_monotone_cache[condition.condition()]
                elif condition.is_monotone() and ConditionCache.mode in ["all", "monotone"]:
                    res = res and ConditionCache.monotone_cache[condition.condition()]
                else:
                    res = False

            return res
        else:
            return False