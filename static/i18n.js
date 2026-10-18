"use strict";
// UI strings. Server-generated alerts are translated by the API (?lang=).
const I18N = {
  en: {
    title: "Smart Health", login: "Sign in", logout: "Log out", username: "Username", password: "Password",
    tab_dashboard: "District dashboard", tab_entry: "Report data", tab_facility: "My facility", tab_forecast: "Forecast",
    facilities: "Facilities", flagged: "Flagged centres", critical: "Critical stock-outs", beds: "Beds occupied",
    flagged_title: "Centres needing intervention", warnings_title: "Early stock-out warnings",
    redistribution_title: "Recommended redistribution", all_centres: "All centres",
    facility: "Facility", medicine: "Medicine", cover: "Days of cover", on_hand: "On hand", reorder: "Suggested reorder",
    score: "Risk score", attendance: "Attendance", tests: "Tests", bedsCol: "Beds", reasons: "Reasons",
    none_found: "Nothing to show.", saved: "Saved.", error: "Something went wrong.",
    stock: "Stock", closing_qty: "Closing stock", consumed: "Consumed today", footfall: "Patient footfall", patients: "Patients today",
    bed_total: "Total beds", bed_occupied: "Occupied beds", attendance_form: "Doctor attendance", doctor: "Doctor name",
    present: "Present", test_audit: "Test availability audit", test_name: "Test name", available: "Available",
    submit: "Submit", choose: "Choose…", forecast_title: "Demand forecast", history: "Actual use", forecast: "Forecast",
    daily_demand: "Forecast daily demand", loading: "Loading…",
  },
  hi: {
    title: "स्मार्ट हेल्थ", login: "साइन इन", logout: "लॉग आउट", username: "उपयोगकर्ता नाम", password: "पासवर्ड",
    tab_dashboard: "जिला डैशबोर्ड", tab_entry: "डेटा दर्ज करें", tab_facility: "मेरा केंद्र", tab_forecast: "पूर्वानुमान",
    facilities: "केंद्र", flagged: "चिह्नित केंद्र", critical: "गंभीर स्टॉक-आउट", beds: "भरे बिस्तर",
    flagged_title: "हस्तक्षेप की ज़रूरत वाले केंद्र", warnings_title: "स्टॉक-आउट की पूर्व चेतावनी",
    redistribution_title: "सुझाया गया पुनर्वितरण", all_centres: "सभी केंद्र",
    facility: "केंद्र", medicine: "दवा", cover: "बचे दिन", on_hand: "उपलब्ध", reorder: "सुझाया गया ऑर्डर",
    score: "जोखिम अंक", attendance: "उपस्थिति", tests: "जाँचें", bedsCol: "बिस्तर", reasons: "कारण",
    none_found: "दिखाने के लिए कुछ नहीं।", saved: "सहेजा गया।", error: "कुछ गड़बड़ हुई।",
    stock: "स्टॉक", closing_qty: "अंतिम स्टॉक", consumed: "आज खपत", footfall: "मरीजों की संख्या", patients: "आज के मरीज",
    bed_total: "कुल बिस्तर", bed_occupied: "भरे बिस्तर", attendance_form: "डॉक्टर उपस्थिति", doctor: "डॉक्टर का नाम",
    present: "उपस्थित", test_audit: "जाँच उपलब्धता ऑडिट", test_name: "जाँच का नाम", available: "उपलब्ध",
    submit: "जमा करें", choose: "चुनें…", forecast_title: "माँग पूर्वानुमान", history: "वास्तविक उपयोग", forecast: "पूर्वानुमान",
    daily_demand: "अनुमानित दैनिक माँग", loading: "लोड हो रहा है…",
  },
  ta: {
    title: "ஸ்மார்ட் ஹெல்த்", login: "உள்நுழை", logout: "வெளியேறு", username: "பயனர் பெயர்", password: "கடவுச்சொல்",
    tab_dashboard: "மாவட்ட முகப்பு", tab_entry: "தரவு பதிவு", tab_facility: "என் மையம்", tab_forecast: "முன்கணிப்பு",
    facilities: "மையங்கள்", flagged: "குறிக்கப்பட்ட மையங்கள்", critical: "அவசர இருப்பு தீர்வு", beds: "நிரம்பிய படுக்கைகள்",
    flagged_title: "தலையீடு தேவைப்படும் மையங்கள்", warnings_title: "இருப்பு தீர்வு முன்னெச்சரிக்கை",
    redistribution_title: "பரிந்துரைக்கப்பட்ட மறுவிநியோகம்", all_centres: "அனைத்து மையங்கள்",
    facility: "மையம்", medicine: "மருந்து", cover: "மீதமுள்ள நாட்கள்", on_hand: "கையிருப்பு", reorder: "பரிந்துரை ஆர்டர்",
    score: "ஆபத்து மதிப்பெண்", attendance: "வருகை", tests: "பரிசோதனைகள்", bedsCol: "படுக்கைகள்", reasons: "காரணங்கள்",
    none_found: "காட்ட எதுவும் இல்லை.", saved: "சேமிக்கப்பட்டது.", error: "ஏதோ தவறு நடந்தது.",
    stock: "இருப்பு", closing_qty: "இறுதி இருப்பு", consumed: "இன்றைய பயன்பாடு", footfall: "நோயாளிகள் வருகை", patients: "இன்றைய நோயாளிகள்",
    bed_total: "மொத்த படுக்கைகள்", bed_occupied: "நிரம்பிய படுக்கைகள்", attendance_form: "மருத்துவர் வருகை", doctor: "மருத்துவர் பெயர்",
    present: "வந்தார்", test_audit: "பரிசோதனை கிடைப்பு தணிக்கை", test_name: "பரிசோதனை பெயர்", available: "கிடைக்கிறது",
    submit: "சமர்ப்பி", choose: "தேர்வு செய்…", forecast_title: "தேவை முன்கணிப்பு", history: "உண்மையான பயன்பாடு", forecast: "முன்கணிப்பு",
    daily_demand: "கணிக்கப்பட்ட தினசரி தேவை", loading: "ஏற்றுகிறது…",
  },
};

// Strings added for the redesigned UI.
Object.assign(I18N.en, {
  tagline: "Real-time health centre management for every PHC and CHC in your district.",
  pt_stock: "Early stock-out warnings", pt_forecast: "AI demand forecasts",
  pt_redistribute: "Smart redistribution", pt_flag: "Automatic centre flagging",
  footfall_trend: "Patient footfall – last 14 days", missing_tests: "Missing tests", all_tests_ok: "All available",
  updated: "Updated", new_alert: "New high-severity alert", bed_occupancy: "Bed occupancy",
  tests_status: "Diagnostic tests", footfall_title: "Patient footfall", days: "days", theme: "Theme",
  welcome: "Signed in as", distance: "km away", units_short: "units", high: "High", medium: "Medium",
});
Object.assign(I18N.hi, {
  tagline: "आपके जिले के हर PHC और CHC के लिए रीयल-टाइम स्वास्थ्य केंद्र प्रबंधन।",
  pt_stock: "स्टॉक-आउट की पूर्व चेतावनी", pt_forecast: "AI माँग पूर्वानुमान",
  pt_redistribute: "स्मार्ट पुनर्वितरण", pt_flag: "केंद्रों की स्वतः पहचान",
  footfall_trend: "मरीजों की संख्या – पिछले 14 दिन", missing_tests: "अनुपलब्ध जाँचें", all_tests_ok: "सभी उपलब्ध",
  updated: "अपडेट", new_alert: "नया उच्च-गंभीरता अलर्ट", bed_occupancy: "बिस्तर अधिभोग",
  tests_status: "नैदानिक जाँचें", footfall_title: "मरीजों की संख्या", days: "दिन", theme: "थीम",
  welcome: "साइन इन:", distance: "किमी दूर", units_short: "इकाई", high: "उच्च", medium: "मध्यम",
});
Object.assign(I18N.ta, {
  tagline: "உங்கள் மாவட்டத்தின் ஒவ்வொரு PHC மற்றும் CHC க்கும் நிகழ்நேர மேலாண்மை.",
  pt_stock: "இருப்பு தீர்வு முன்னெச்சரிக்கை", pt_forecast: "AI தேவை முன்கணிப்பு",
  pt_redistribute: "ஸ்மார்ட் மறுவிநியோகம்", pt_flag: "மையங்களை தானாகக் குறிப்பது",
  footfall_trend: "நோயாளிகள் வருகை – கடந்த 14 நாட்கள்", missing_tests: "இல்லாத பரிசோதனைகள்", all_tests_ok: "அனைத்தும் உள்ளன",
  updated: "புதுப்பிப்பு", new_alert: "புதிய உயர் முன்னுரிமை எச்சரிக்கை", bed_occupancy: "படுக்கை நிரம்பல்",
  tests_status: "பரிசோதனைகள்", footfall_title: "நோயாளிகள் வருகை", days: "நாட்கள்", theme: "தீம்",
  welcome: "உள்நுழைந்தவர்:", distance: "கி.மீ தொலைவு", units_short: "அலகு", high: "உயர்", medium: "நடுத்தர",
});

Object.assign(I18N.en, { status: "Status" });
Object.assign(I18N.hi, { status: "स्थिति" });
Object.assign(I18N.ta, { status: "நிலை" });
