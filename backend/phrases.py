"""Fixed, safe referral phrases for English and Hindi."""

REFERRAL_PHRASES = {
    "en": {
        "urgent": (
            "Your response needs prompt attention. "
            "Please contact a qualified healthcare worker "
            "or visit the nearest health facility."
        ),
        "emergency": (
            "This may require emergency help. "
            "Please contact local emergency services or go "
            "to the nearest emergency department now."
        ),
        "general": (
            "I cannot diagnose or recommend treatment. "
            "Please discuss this with a qualified healthcare worker."
        ),
    },
    "hi": {
        "urgent": (
            "आपके जवाब पर जल्द ध्यान देने की जरूरत हो सकती है। "
            "कृपया स्वास्थ्य कर्मचारी से संपर्क करें या नजदीकी स्वास्थ्य केंद्र जाएं।"
        ),
        "emergency": (
            "इस स्थिति में आपातकालीन सहायता की जरूरत हो सकती है। "
            "कृपया तुरंत स्थानीय आपातकालीन सेवा से संपर्क करें "
            "या नजदीकी अस्पताल के आपातकालीन विभाग में जाएं।"
        ),
        "general": (
            "मैं बीमारी की पहचान या इलाज की सलाह नहीं दे सकता। "
            "कृपया योग्य स्वास्थ्य कर्मचारी से बात करें।"
        ),
    },
}


def get_referral_phrase(language="en", level="general"):
    """Return a fixed referral phrase in the selected language."""
    language = language if language in REFERRAL_PHRASES else "en"
    level = level if level in REFERRAL_PHRASES[language] else "general"
    return REFERRAL_PHRASES[language][level]
