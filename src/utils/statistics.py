class Statistics:
    statistics = {}

    @staticmethod
    def reset():
        Statistics.statistics = {}

    @staticmethod
    def log_asp_solver_time(time_taken: float):
        Statistics.statistics["asp_solver_time"] = Statistics.statistics.get("asp_solver_time", 0.0) + time_taken

    @staticmethod
    def log_solver_cached_prompt_hit():
        Statistics.statistics["solver_cached_prompt_hit"] = Statistics.statistics.get("solver_cached_prompt_hit", 0) + 1


    @staticmethod
    def log_solver_call():
        Statistics.statistics["solver_calls"] = Statistics.statistics.get("solver_calls", 0) + 1

    @staticmethod
    def log_llm_call(tokens_in: int, tokens_out: int):
        Statistics.statistics["llm_calls"] = Statistics.statistics.get("llm_calls", 0) + 1
        Statistics.statistics["llm_tokens_in"] = Statistics.statistics.get("llm_tokens_in", 0) + tokens_in
        Statistics.statistics["llm_tokens_out"] = Statistics.statistics.get("llm_tokens_out", 0) + tokens_out

    @staticmethod
    def log_llm_call_duration(duration: float):
        Statistics.statistics["llm_call_duration"] = Statistics.statistics.get("llm_call_duration", 0) + duration 

    @staticmethod
    def log_non_monotone_cache_invalidation():
        Statistics.statistics["non_monotone_cache_invalidations"] = Statistics.statistics.get("non_monotone_cache_invalidations", 0) + 1
    
    @staticmethod
    def log_monotone_cache_invalidation():
        Statistics.statistics["monotone_cache_invalidations"] = Statistics.statistics.get("monotone_cache_invalidations", 0) + 1
    @staticmethod
    def log_cache_hit_monotone():
        Statistics.statistics["cache_hits_monotone"] = Statistics.statistics.get("cache_hits_monotone", 0) + 1

    @staticmethod
    def log_cache_miss_monotone():
        Statistics.statistics["cache_miss_monotone"] = Statistics.statistics.get("cache_miss_monotone", 0) + 1

    @staticmethod
    def log_cache_solver_skip_counter():
        Statistics.statistics["solver_skip_counter"] = Statistics.statistics.get("solver_skip_counter", 0) + 1

    @staticmethod
    def log_cache_hit_non_monotone():
        Statistics.statistics["cache_hits_non_monotone"] = Statistics.statistics.get("cache_hits_non_monotone", 0) + 1

    @staticmethod
    def log_cache_miss_non_monotone():
        Statistics.statistics["cache_miss_non_monotone"] = Statistics.statistics.get("cache_miss_non_monotone", 0) + 1

    @staticmethod
    def get_stats():
        return Statistics.statistics.copy()
    
    @staticmethod
    def get_statistics_since(previous_stats: dict):
        current_stats = Statistics.get_stats()
        delta_stats = {}
        for key in current_stats:
            delta_stats[key] = current_stats[key] - previous_stats.get(key, 0)
        return delta_stats