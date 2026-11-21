"""
Fixed, non-LLM-generated user-facing phrases for English and Hindi.
Review translations with fluent speakers before real-world deployment.
"""

PHRASES = {
    "en": {
        "welcome": "Hello. I can help you record the visit.",
        "disclosure": "I am an AI assistant, not a human.",
        "listening": "I am listening.",
        "confirm": "Please confirm the information.",
        "saved": "The information has been saved.",
        "danger_alert": "A possible danger sign has been detected.",
        "refer_now": (
            "A possible danger sign has been detected. "
            "Please arrange immediate referral to the nearest appropriate health facility "
            "and follow your approved local referral protocol."
        ),
        "connection_lost": "Connection lost. Your current form is saved on this device.",
        "reconnecting": "Reconnecting. Please wait.",
    },
    "hi": {
        "welcome": "नमस्ते। मैं आपकी विज़िट की जानकारी दर्ज करने में मदद कर सकता हूँ।",
        "disclosure": "मैं एक AI सहायक हूँ, इंसान नहीं।",
        "listening": "मैं सुन रहा हूँ।",
        "confirm": "कृपया जानकारी की पुष्टि करें।",
        "saved": "जानकारी सुरक्षित कर दी गई है।",
        "danger_alert": "संभावित खतरे का संकेत मिला है।",
        "refer_now": (
            "संभावित खतरे का संकेत मिला है। कृपया तुरंत निकटतम उपयुक्त स्वास्थ्य केंद्र "
            "से संपर्क करें और स्वीकृत स्थानीय रेफरल प्रक्रिया का पालन करें।"
        ),
        "connection_lost": "कनेक्शन टूट गया है। आपकी मौजूदा जानकारी इस डिवाइस पर सुरक्षित है।",
        "reconnecting": "दोबारा कनेक्ट किया जा रहा है। कृपया प्रतीक्षा करें।",
    },
}


def get_phrase(language: str, key: str) -> str:
    """Return a fixed phrase; safely fall back to English."""
    lang = (language or "en").lower()
    if lang not in PHRASES:
        lang = "en"
    return PHRASES[lang].get(key, PHRASES["en"].get(key, key))


if __name__ == "__main__":
    print(get_phrase("en", "disclosure"))
    print(get_phrase("hi", "refer_now"))
