from typing import Any, Dict, Tuple


def rule_based_intent_and_action(text: str) -> Tuple[str, float, str]:
    """
    Very small keyword-based fallback to detect intent and suggest action.
    Returns (intent, confidence_estimate, suggested_action)
    """
    if not text:
        return "unknown", 0.0, "no-action"

    txt = text.lower()
    # Interested signals
    interested_keywords = ["interested", "price", "pricing", "details", "need details", "can you share"]
    for k in interested_keywords:
        if k in txt:
            return "interested", 0.75, "send_pricing"

    # Not interested signals
    not_interested_keywords = ["not interested", "no thanks", "no thank", "don't need", "do not need"]
    for k in not_interested_keywords:
        if k in txt:
            return "not_interested", 0.8, "close_thread"

    # Escalation signals
    escalate_keywords = ["manager", "supervisor", "escalat", "complain", "urgent"]
    for k in escalate_keywords:
        if k in txt:
            return "escalate", 0.9, "escalate_to_ops"

    return "unknown", 0.0, "no-action"


class ActionRule:
    def __init__(self, intent: str, action: str):
        self.intent = intent
        self.action = action


class RulesEngine:
    def __init__(self):
        self.rules: Dict[str, ActionRule] = {}

    def add_rule(self, intent: str, action: str):
        self.rules[intent] = ActionRule(intent, action)

    def get_action(self, intent: str) -> Any:
        rule = self.rules.get(intent)
        if rule:
            return rule.action
        return None

    def list_rules(self) -> Dict[str, str]:
        return {intent: rule.action for intent, rule in self.rules.items()}
