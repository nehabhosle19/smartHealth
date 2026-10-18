"""Server-side message catalogue (English, Hindi, Tamil) for alerts and recommendations."""
from __future__ import annotations

DEFAULT_LANG = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "level_critical": "Critical",
        "level_warning": "Warning",
        "level_ok": "OK",
        "stockout": "{medicine} at {facility}: about {days} day(s) of stock left",
        "stockout_empty": "{medicine} at {facility}: out of stock",
        "transfer": "Move {qty} {unit} of {medicine} from {source} to {target} ({km} km)",
        "stock_critical": "{count} medicine(s) at critical level (under 3 days of cover)",
        "stock_warning": "{count} medicine(s) below replenishment lead-time cover",
        "beds_full": "Bed occupancy at {pct}%",
        "low_attendance": "Doctor attendance only {pct}% over the last 7 days",
        "low_tests": "Only {pct}% of audited diagnostic tests are available",
        "footfall_surge": "Patient footfall up {pct}% versus the previous fortnight",
        "stale_data": "No data reported for {days} day(s)",
    },
    "hi": {
        "level_critical": "गंभीर",
        "level_warning": "चेतावनी",
        "level_ok": "सामान्य",
        "stockout": "{facility} में {medicine}: लगभग {days} दिन का स्टॉक बचा है",
        "stockout_empty": "{facility} में {medicine}: स्टॉक समाप्त",
        "transfer": "{source} से {target} को {medicine} की {qty} {unit} भेजें ({km} किमी)",
        "stock_critical": "{count} दवा(एँ) गंभीर स्तर पर (3 दिन से कम का स्टॉक)",
        "stock_warning": "{count} दवा(एँ) पुनःपूर्ति समय से कम स्टॉक पर",
        "beds_full": "बिस्तर अधिभोग {pct}%",
        "low_attendance": "पिछले 7 दिनों में डॉक्टर उपस्थिति केवल {pct}%",
        "low_tests": "जाँची गई नैदानिक परीक्षाओं में से केवल {pct}% उपलब्ध हैं",
        "footfall_surge": "पिछले पखवाड़े की तुलना में मरीजों की संख्या {pct}% बढ़ी",
        "stale_data": "{days} दिन से कोई डेटा दर्ज नहीं हुआ",
    },
    "ta": {
        "level_critical": "அவசரம்",
        "level_warning": "எச்சரிக்கை",
        "level_ok": "சரி",
        "stockout": "{facility} இல் {medicine}: சுமார் {days} நாட்களுக்கு மட்டுமே இருப்பு உள்ளது",
        "stockout_empty": "{facility} இல் {medicine}: இருப்பு இல்லை",
        "transfer": "{source} இலிருந்து {target} க்கு {medicine} {qty} {unit} அனுப்பவும் ({km} கி.மீ)",
        "stock_critical": "{count} மருந்து(கள்) அவசர நிலையில் (3 நாட்களுக்கும் குறைவான இருப்பு)",
        "stock_warning": "{count} மருந்து(கள்) மறுநிரப்பு கால அளவை விடக் குறைவாக உள்ளது",
        "beds_full": "படுக்கை நிரம்பல் {pct}%",
        "low_attendance": "கடந்த 7 நாட்களில் மருத்துவர் வருகை {pct}% மட்டுமே",
        "low_tests": "தணிக்கை செய்த பரிசோதனைகளில் {pct}% மட்டுமே கிடைக்கின்றன",
        "footfall_surge": "முந்தைய இரு வாரங்களை விட நோயாளிகள் வருகை {pct}% உயர்வு",
        "stale_data": "{days} நாட்களாக தரவு பதிவு செய்யப்படவில்லை",
    },
}


def resolve_lang(header_or_code: str | None) -> str:
    """Pick a supported language from a ?lang code or an Accept-Language header."""
    if not header_or_code:
        return DEFAULT_LANG
    for part in header_or_code.split(","):
        code = part.split(";")[0].strip().lower().split("-")[0]
        if code in MESSAGES:
            return code
    return DEFAULT_LANG


def t(lang: str, key: str, **params) -> str:
    template = MESSAGES.get(lang, {}).get(key) or MESSAGES[DEFAULT_LANG][key]
    return template.format(**params)
