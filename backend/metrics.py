import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TokenMetrics:
    """Track token usage across API calls"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset metrics for a new query"""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.api_calls = []
        self.start_time = None
    
    def start(self):
        """Mark the start of a query processing"""
        self.reset()
        self.start_time = datetime.now()
    
    def add_tokens(self, call_type, input_tokens, output_tokens):
        """Log a single API call's token usage"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        
        call_info = {
            "type": call_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "timestamp": datetime.now().isoformat()
        }
        
        self.api_calls.append(call_info)
        
        logger.info(
            f"[TOKEN] {call_type}: "
            f"In={input_tokens}, Out={output_tokens}, "
            f"Total={input_tokens + output_tokens}"
        )
    
    def get_total_tokens(self):
        """Get total tokens used in this session"""
        return self.total_input_tokens + self.total_output_tokens
    
    def get_metrics_summary(self):
        """Get a summary of token metrics"""
        elapsed_time = None
        if self.start_time:
            elapsed_time = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.get_total_tokens(),
            "api_calls_count": len(self.api_calls),
            "api_calls": self.api_calls,
            "elapsed_seconds": elapsed_time
        }
    
    def log_summary(self):
        """Log a summary of all metrics"""
        metrics = self.get_metrics_summary()
        logger.info(
            f"[TOKEN SUMMARY] Total: {metrics['total_tokens']} tokens | "
            f"Input: {metrics['input_tokens']} | Output: {metrics['output_tokens']} | "
            f"API Calls: {metrics['api_calls_count']} | "
            f"Time: {(metrics['elapsed_seconds'] or 0):.2f}s"
        )


# Global metrics instance
token_metrics = TokenMetrics()
