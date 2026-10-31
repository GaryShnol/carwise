"""Every text the UI shows itself, in Hebrew; the answers come from the pipeline.

Why a module with no imports: the Streamlit script shows the title and the
loading message before it imports the heavy modules (torch, chromadb, openai),
so a cold start shows a loading state instead of a blank page.
"""

TITLE = "carwise: שאלות על שמונה רכבים שנבחנו"
LOADING = (
    "טוען את מודל החיפוש ואת האינדקס. בהפעלה הראשונה הכתבות והמודל יורדים "
    "והאינדקס נבנה, וזה יכול לקחת כמה דקות..."
)
THINKING = "חושב..."
INPUT_PLACEHOLDER = "שאלה על אחד משמונת הרכבים..."
SIDEBAR_TITLE = "ההעדפות שלך"
SIDEBAR_HELP = "מה שהבנתי מהשיחה עד עכשיו. ההעדפות נשמרות רק לשיחה הזאת."
SOURCE_PREFIX = "מתוך"
RESET_BUTTON = "שיחה חדשה"
SOURCES_TITLE = "מקורות ({count} קטעים שנשלפו)"
SOURCES_HEADERS = ("רכב", "פרק", "ציון", "צוטט")
CITED_MARK = "✓"
ARTICLES_PREFIX = "הכתבות המלאות"
SESSION_COST = "עלות השיחה עד עכשיו: ${cost:.4f}"
STOPPED = "השיחה נעצרה כי הגיעה למגבלת העלות. כדי להתחיל מחדש יש לרענן את הדף."
MISSING_KEY = (
    "לא הוגדר מפתח API של OpenAI, ולכן אי אפשר לענות על שאלות. "
    "יש להגדיר את משתנה הסביבה OPENAI_API_KEY (למשל בקובץ ‎.env‎) ולהפעיל מחדש."
)
INDEX_MISSING = "האינדקס של הכתבות עוד לא נבנה. יש להריץ קודם ‎python -m app ingest‎ ולהפעיל מחדש."
FIRST_START_FAILED = (
    "לא הצלחתי להוריד את הכתבות או לבנות את האינדקס בהפעלה הראשונה. אפשר לרענן את "
    "הדף כדי לנסות שוב, או להניח את קובצי הכתבות בתיקייה data/raw שבנפח הנתונים "
    "ולהפעיל מחדש."
)
UNEXPECTED = "משהו השתבש בצד שלנו. אפשר לנסות שוב בעוד רגע."
