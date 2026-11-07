import os
import sys
import re
import json
import requests
from bs4 import BeautifulSoup
from collections import defaultdict

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WIKIPEDIA_API_KEY = os.environ.get("WIKIPEDIA_API_KEY", "").strip()
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "").strip()
SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gujarat_colleges_scraped.json")

PAGE_CACHE = {}
INSTITUTIONS = []

def get_headers() -> dict:
    headers = {
        "User-Agent": "GujaratScienceEducationQA/10.0 (contact: science-education@gujarat.edu)"
    }
    if WIKIPEDIA_API_KEY:
        headers["Authorization"] = f"Bearer {WIKIPEDIA_API_KEY}"
    return headers

def clean_text(text: str) -> str:
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r"\[\d+\]|\[[a-zA-Z ]+\]", "", text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def load_data():
    global PAGE_CACHE, INSTITUTIONS
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    PAGE_CACHE = d.get("page_cache", {})
                    INSTITUTIONS = d.get("institutions", [])
                    if INSTITUTIONS:
                        return
        except Exception:
            pass

def save_cache():
    try:
        data = {
            "institutions": INSTITUTIONS,
            "page_cache": PAGE_CACHE
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

load_data()

def fetch_wiki_page(title: str) -> tuple[str, str]:
    norm = title.lower().strip()
    if norm in PAGE_CACHE and PAGE_CACHE[norm].get("extract"):
        return PAGE_CACHE[norm]["title"], PAGE_CACHE[norm]["extract"]

    for k, v in PAGE_CACHE.items():
        if norm in k or k in norm:
            if v.get("extract"):
                return v["title"], v["extract"]

    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
        "format": "json"
    }
    try:
        resp = requests.get(WIKIPEDIA_API_URL, params=params, headers=get_headers(), timeout=12)
        if resp.status_code == 200:
            pages = resp.json().get("query", {}).get("pages", {})
            for pid, p in pages.items():
                if pid != "-1" and p.get("extract"):
                    t = p.get("title", title)
                    ext = p.get("extract", "")
                    PAGE_CACHE[norm] = {"title": t, "extract": ext}
                    save_cache()
                    return t, ext
    except Exception:
        pass
    return title, ""

def search_wiki(query: str, limit: int = 5) -> list[str]:
    clean_q = re.sub(r'^(tell me about|what is|who is|can you tell me about|details of|give information about|information on|about)\s+', '', query.strip(), flags=re.IGNORECASE).strip()
    if not clean_q:
        clean_q = query.strip()

    params = {
        "action": "query",
        "list": "search",
        "srsearch": f"{clean_q} Gujarat",
        "srlimit": limit,
        "format": "json"
    }
    try:
        resp = requests.get(WIKIPEDIA_API_URL, params=params, headers=get_headers(), timeout=10)
        if resp.status_code == 200:
            titles = [item["title"] for item in resp.json().get("query", {}).get("search", [])]
            disallowed = ["gujarat", "history of gujarat", "geography of gujarat", "2002 gujarat violence", "gujarat riots"]
            return [t for t in titles if t.lower() not in disallowed]
    except Exception:
        pass
    return []

def query_search_api(query: str) -> str:
    if SERPAPI_API_KEY:
        try:
            resp = requests.get("https://serpapi.com/search.json", params={
                "q": query + " Gujarat higher education science",
                "api_key": SERPAPI_API_KEY,
                "num": 4
            }, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                snippets = []
                if "answer_box" in data and "answer" in data["answer_box"]:
                    snippets.append(data["answer_box"]["answer"])
                for res in data.get("organic_results", [])[:4]:
                    if "snippet" in res:
                        snippets.append(f"- {res['title']}: {res['snippet']}")
                if snippets:
                    return "\n\n".join(snippets)
        except Exception:
            pass

    if SEARCH_API_KEY and GOOGLE_CSE_ID:
        try:
            resp = requests.get("https://www.googleapis.com/customsearch/v1", params={
                "q": query + " Gujarat science education",
                "key": SEARCH_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "num": 4
            }, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                snippets = [f"- {item['title']}: {item.get('snippet', '')}" for item in data.get("items", [])[:4]]
                if snippets:
                    return "\n\n".join(snippets)
        except Exception:
            pass

    return ""

def extractive_sentence_qa(query: str, text: str) -> str:
    if not text:
        return ""
    if not HAS_SKLEARN:
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        return "\n\n".join(paras[:2])

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip().split()) >= 4]
    if len(sentences) <= 3:
        return text.strip()

    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        tfidf_mat = vec.fit_transform(sentences + [query])
        query_vec = tfidf_mat[-1]
        doc_vecs = tfidf_mat[:-1]
        scores = (doc_vecs * query_vec.T).toarray().flatten()
        top_indices = np.argsort(scores)[::-1]

        selected_indices = [i for i in top_indices[:4] if scores[i] > 0.08]
        if not selected_indices:
            selected_indices = list(range(min(3, len(sentences))))
        else:
            selected_indices.sort()

        result_paras = []
        for idx in selected_indices:
            s = sentences[idx]
            if s and not any(s in p for p in result_paras):
                result_paras.append(s)
        return " ".join(result_paras)
    except Exception:
        return text[:400]

def find_science_college(query: str) -> dict:
    q_lower = query.lower()

    # Generic institution category queries should NOT match a single college
    generic_blocks = [
        "government engineering", "govt engineering", "private university", "private universities",
        "medical college", "medical colleges", "pharmacy college", "pharmacy colleges",
        "top engineering", "top medical", "best engineering", "best medical", "best branch",
        "which branch", "colleges in", "universities in", "colleges for", "universities for"
    ]
    if any(gb in q_lower for gb in generic_blocks) and not any(spec in q_lower for spec in ["bjmc", "ldce", "vgec", "daiict", "da-iict", "nirma", "pdeu", "svnit", "iitgn", "iit gandhinagar", "bvm", "msu", "cept", "ddu", "parul", "adani", "silver oak", "indus", "lj"]):
        return None

    alias_map = {
        "iit gandhinagar": "iitgn", "iitgn": "iitgn", "iit gn": "iitgn", "iit g": "iitgn",
        "svnit": "svnit", "svnit surat": "svnit", "nit surat": "svnit",
        "da-iict": "daiict", "daiict": "daiict", "dhirubhai ambani": "daiict", "dau": "daiict",
        "nirma": "nirma", "nirma university": "nirma", "itnu": "nirma",
        "pdeu": "pdeu", "pdpu": "pdeu", "pandit deendayal": "pdeu",
        "ldce": "ldce", "ld college": "ldce", "l.d. college": "ldce", "lalbhai dalpatbhai": "ldce",
        "vgec": "vgec", "vishwakarma": "vgec",
        "bvm": "bvm", "birla vishvakarma": "bvm", "birla vishwakarma": "bvm",
        "msu": "msu", "msu baroda": "msu", "maharaja sayajirao": "msu",
        "iiit vadodara": "iiitv", "iiitv": "iiitv",
        "iiit surat": "iiits", "iiits": "iiits",
        "iitram": "iitram",
        "charusat": "charusat", "charotar": "charusat", "cspit": "charusat", "depstar": "charusat",
        "ahmedabad university": "ahmedabad_univ", "seas": "ahmedabad_univ",
        "cept": "cept", "cept university": "cept",
        "ddu": "ddu", "dharmsinh desai": "ddu",
        "parul": "parul", "parul university": "parul",
        "bjmc": "bjmc", "b.j. medical": "bjmc", "bj medical": "bjmc", "civil hospital medical": "bjmc",
        "gmc baroda": "gmc_baroda", "medical college baroda": "gmc_baroda", "ssg hospital": "gmc_baroda",
        "gmc surat": "gmc_surat", "medical college surat": "gmc_surat",
        "gmc rajkot": "gmc_rajkot", "pdu medical": "gmc_rajkot",
        "gmers sola": "gmers_sola", "sola medical": "gmers_sola",
        "nhl medical": "nhl_medical", "nhl mmc": "nhl_medical", "v.s. hospital": "nhl_medical",
        "lmcp": "lmcp", "lm college of pharmacy": "lmcp", "l.m. college": "lmcp",
        "bk mody": "bk_mody", "b.k. mody": "bk_mody",
        "niper": "niper", "niper ahmedabad": "niper",
        "aau": "aau", "anand agricultural": "aau",
        "kamdhenu": "kamdhenu", "veterinary college": "kamdhenu",
        "gtu": "gtu", "gujarat technological": "gtu",
        "gbu": "gbu", "gujarat biotechnology": "gbu",
        "lj": "lj_university", "lj university": "lj_university", "ljiet": "lj_university",
        "adani": "adani_university", "adani university": "adani_university", "aiie": "adani_university",
        "silver oak": "silver_oak_u", "silver oak university": "silver_oak_u", "socet": "silver_oak_u",
        "indus": "indus_univer", "indus university": "indus_univer", "iite": "indus_univer",
        "rai university": "rai_university", "rai": "rai_university"
    }

    for phrase, cid in alias_map.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', q_lower):
            for c in INSTITUTIONS:
                if c.get("id") == cid or cid in c.get("name", "").lower():
                    return c
            break

    for c in INSTITUTIONS:
        full_name = c.get("name", "").lower()
        base_name = re.sub(r'\(.*?\)', '', full_name).strip()
        # Avoid matching generic institutional phrases
        if base_name in ["government engineering college", "government medical college", "private university"]:
            continue
        if base_name and len(base_name) > 6 and base_name in q_lower:
            return c
    return None

def format_college_list(title: str, colleges: list[dict], note: str = "") -> str:
    count = len(colleges)
    if count == 0:
        return f"No verified institutions found matching **{title}** in Gujarat."

    out = [
        f"### {title}\n",
        f"Here are the **{count}** verified institutions matching your criteria in Gujarat:\n"
    ]
    for idx, c in enumerate(colleges, 1):
        out.append(f"#### {idx}. {c['name']}")
        out.append(f"- **Location:** {c.get('city')}")
        out.append(f"- **Institution Type:** {c.get('type')}")
        if c.get("nirf_rank"):
            out.append(f"- **Standing / Recognition:** {c.get('nirf_rank')}")
        if c.get("fees") and c.get("fees") != "N/A":
            out.append(f"- **Annual Fees:** {c.get('fees')}")
        if c.get("avg_package") and c.get("avg_package") != "N/A":
            pkg_str = f"Average {c.get('avg_package')}"
            if c.get("highest_package"):
                pkg_str += f" | Highest {c.get('highest_package')}"
            out.append(f"- **Placements:** {pkg_str}")
        if c.get("exams"):
            out.append(f"- **Entrance Exams:** {', '.join(c.get('exams'))}")
        if c.get("cutoffs"):
            out.append(f"- **Cutoff Trends:** {c.get('cutoffs')}")
        if c.get("overview"):
            out.append(f"- **Overview:** {c.get('overview')}")
        out.append("")

    if note:
        out.append(note)

    return clean_text("\n".join(out))

def parse_and_filter_institutions(clean_q: str) -> str | None:
    q_lower = clean_q.lower()

    # City mapping (canonical -> aliases including common misspellings/slang)
    city_map = {
        "ahmedabad": ["ahmedabad", "ahemdabad", "ahmadabad", "amdavad", "ahmd"],
        "gandhinagar": ["gandhinagar", "gandhi nagar"],
        "vadodara": ["vadodara", "baroda"],
        "surat": ["surat"],
        "rajkot": ["rajkot"],
        "anand": ["anand", "vallabh vidyanagar", "vidyanagar", "vvn"],
        "nadiad": ["nadiad"],
        "bhavnagar": ["bhavnagar"],
        "mehsana": ["mehsana", "mahesana"],
        "morbi": ["morbi"],
        "bharuch": ["bharuch"],
        "valsad": ["valsad"],
        "dahod": ["dahod"],
        "patan": ["patan"],
        "godhra": ["godhra"],
        "modasa": ["modasa"],
        "bhuj": ["bhuj", "kutch"],
        "jamnagar": ["jamnagar"],
        "junagadh": ["junagadh"]
    }

    matched_city = None
    matched_city_label = None
    for canonical_city, aliases in city_map.items():
        if any(re.search(r'\b' + re.escape(alias) + r'\b', q_lower) for alias in aliases):
            matched_city = canonical_city
            matched_city_label = canonical_city.title()
            break

    # Ownership / Management
    is_pvt = bool(re.search(r'\b(private|pvt|self[\s-]?financed|sfi)\b', q_lower))
    is_gov = bool(re.search(r'\b(government|govt|state\s+colleges?|public|grant[\s-]?in[\s-]?aid|gmers)\b', q_lower))
    only_univ = bool(re.search(r'\b(universit(?:y|ies)|deemed)\b', q_lower))

    # Discipline / Degree
    discipline = None
    disc_label = ""
    if re.search(r'\b(b\.?tech|b\.?e\.?|engineerings?|technolog(?:y|ical)|technical)\b', q_lower):
        discipline = "engineering"
        disc_label = "B.Tech / Engineering"
    elif re.search(r'\b(computer|cse|cs\b|it\b|information technology|software|ai\b|data science)\b', q_lower):
        discipline = "computer"
        disc_label = "Computer Engineering / IT"
    elif re.search(r'\b(medicals?|mbbs|dentals?|bds|ayush|bams|bhms|doctors?)\b', q_lower):
        discipline = "medical"
        disc_label = "Medical (MBBS/BDS)"
    elif re.search(r'\b(pharmac(?:y|ies)|b\.?pharm|d\.?pharm)\b', q_lower):
        discipline = "pharmacy"
        disc_label = "Pharmacy (B.Pharm)"
    elif re.search(r'\b(architectures?|b\.?arch|plannings?|b\.?plan)\b', q_lower):
        discipline = "architecture"
        disc_label = "Architecture / Planning"
    elif re.search(r'\b(agricultur(?:e|al)|horticultur(?:e|al)|forestry|fisheries)\b', q_lower):
        discipline = "agriculture"
        disc_label = "Agriculture & Allied Sciences"
    elif re.search(r'\b(veterinar(?:y|ies)|b\.?v\.?sc|dairy)\b', q_lower):
        discipline = "veterinary"
        disc_label = "Veterinary Science"
    elif re.search(r'\b(paramedicals?|physiotherap(?:y|ies)|bpt|nursings?)\b', q_lower):
        discipline = "paramedical"
        disc_label = "Paramedical / Physiotherapy"

    # Exclude queries that are specifically asking about fees, cutoffs, syllabus, or JEE Main
    if re.search(r'\b(fees?|fee structure|costs?|tuitions?|cutoffs?|cut off|closing ranks?|syllabus|jee main)\b', q_lower):
        return None

    # Identify if query indicates an institution listing/filtering intent
    listing_keywords = [
        "give me", "names of", "name of", "list of", "list", "show me", "which colleges", "which universities",
        "which institutes", "colleges in", "universities in", "colleges of", "universities of",
        "options in", "institutes in", "colleges near", "universities near", "colleges for", "universities for"
    ]
    has_listing_intent = any(k in q_lower for k in listing_keywords) or \
                         (matched_city and (discipline or is_pvt or is_gov or only_univ)) or \
                         (is_pvt and (discipline or only_univ)) or \
                         (is_gov and (discipline or only_univ))

    if not has_listing_intent:
        return None

    colleges = []
    for c in INSTITUTIONS:
        c_city = c.get("city", "").lower()
        c_name = c.get("name", "").lower()
        c_type = c.get("type", "").lower()
        c_cat = c.get("category", "").lower()
        c_discs = [d.lower() for d in c.get("disciplines", [])]
        c_is_gov = c.get("is_government", False)

        if matched_city:
            if matched_city not in c_city and matched_city not in c_name:
                continue

        if is_gov and not c_is_gov:
            continue
        if is_pvt and c_is_gov:
            continue

        if only_univ and ("university" not in c_type and "university" not in c_name and "deemed" not in c_type):
            continue

        if discipline:
            if discipline == "computer":
                if "computer" not in c_discs:
                    continue
            elif discipline == "engineering":
                if c_cat != "engineering" and "engineering" not in c_discs:
                    continue
            elif discipline == "medical":
                if c_cat != "medical" and "medical" not in c_discs:
                    continue
            elif discipline == "pharmacy":
                if c_cat != "pharmacy" and "pharmacy" not in c_discs:
                    continue
            elif discipline == "architecture":
                if c_cat != "architecture" and "architecture" not in c_discs:
                    continue
            elif discipline == "agriculture":
                if c_cat != "agriculture" and "agriculture" not in c_discs:
                    continue
            elif discipline == "veterinary":
                if c_cat != "veterinary" and "veterinary" not in c_discs:
                    continue
            elif discipline == "paramedical":
                if c_cat != "paramedical" and "paramedical" not in c_discs:
                    continue

        colleges.append(c)

    parts = []
    if is_pvt:
        parts.append("Private")
    elif is_gov:
        parts.append("Government")

    if only_univ:
        parts.append("Universities")
    else:
        parts.append("Colleges & Universities")

    if matched_city_label:
        parts.append(f"in {matched_city_label}")
    else:
        parts.append("in Gujarat")

    if disc_label:
        parts.append(f"for {disc_label}")

    title = " ".join(parts)

    note = ""
    if matched_city == "ahmedabad" and discipline == "engineering":
        note = "> [!NOTE]\n> **Gandhinagar / Twin-City Regional Options:** Located just adjacent to Ahmedabad along the SG Highway and Gandhinagar knowledge corridor are top premier universities including **DA-IICT (Dhirubhai Ambani University)** and **PDEU (Pandit Deendayal Energy University)**."

    return format_college_list(title, colleges, note)

# ==============================================================================
# 12th SCIENCE DOMAIN KNOWLEDGE MODULES (GUJARAT ONLY)
# ==============================================================================

def get_after_12th_science_overview() -> str:
    return clean_text("""### Comprehensive Higher Education Guide: After 12th Science in Gujarat

In Gujarat, Class 12 Science (GSEB / CBSE) is divided into **Group A (Mathematics)**, **Group B (Biology)**, and **Group AB (Maths + Biology)**. Each pathway opens specialized, high-demand professional degree courses across the state.

---

#### 1. Group A (Physics, Chemistry, Mathematics):
- **B.E. / B.Tech (Engineering & Technology):**
  - **Admission Authority:** **ACPC** (Admission Committee for Professional Courses).
  - **Merit Formula:** **50% Board PCM theory marks + 50% GUJCET percentile**. (All India quota: JEE Main).
  - **Top Branches:** Computer Engineering, IT, AI & Data Science, ECE/VLSI, Chemical, Mechanical, Civil, Electrical, Petroleum.
  - **Top Colleges:** IIT Gandhinagar, SVNIT Surat, DA-IICT Gandhinagar, Nirma University, PDEU, LDCE Ahmedabad, VGEC, BVM Anand, MSU Baroda.
- **B.Arch (Architecture - 5 Years):**
  - **Admissions:** Via ACPC based on **NATA score (50%) + Class 12 Board (50%)**.
  - **Top Colleges:** CEPT University Ahmedabad (Ranked #1 in Gujarat), MSU Baroda, Nirma University.
- **B.Plan (Urban & Regional Planning - 4 Years):** CEPT University, SVNIT Surat (via JEE Main Paper 2 / ACPC).
- **BCA & B.Sc (IT / Data Science / Pure Sciences):** Centralized admission via **GCAS (Gujarat Common Admission Services)** across state universities.
- **Defense & Aviation:** NDA entrance (UPSC) for Air Force/Navy; Commercial Pilot Training (GUJSAIL, AAA Ahmedabad).

---

#### 2. Group B (Physics, Chemistry, Biology):
- **MBBS & BDS (Medical & Dental - 5.5 / 5 Years):**
  - **Admission Authority:** **ACPUGMEC** (Admission Committee for Professional Undergraduate Medical Educational Courses).
  - **Qualifying Exam:** **NEET-UG** (100% merit for 85% Gujarat State Quota).
  - **Top Colleges:** B.J. Medical College (BJMC) Ahmedabad, GMC Baroda, GMC Surat, GMC Rajkot, 13 GMERS Medical Colleges.
- **AYUSH Courses (BAMS - Ayurveda & BHMS - Homeopathy):**
  - ITRA Jamnagar (National Importance), Govt Akhandanand Ahmedabad via ACPUGMEC.
- **Physiotherapy (BPT - 4.5 Years) & Paramedical:**
  - Very high demand in Gujarat! Administered by Gujarat Paramedical Admission Committee (Civil Hospital Ahmedabad, Vadodara, KM Patel Karamsad).
- **Pharmacy (B.Pharm - 4 Years & D.Pharm - 2 Years):**
  - Via **ACPC** (50% Board PCB theory + 50% GUJCET).
  - Top Colleges: LMCP Ahmedabad, Institute of Pharmacy Nirma, NIPER Ahmedabad, BK Mody Rajkot, CHARUSAT.
- **Veterinary Science (B.V.Sc & A.H. - 5.5 Years):**
  - Administered by **Kamdhenu University** on NEET-UG merit (Veterinary Colleges at Anand, Junagadh, Navsari, Sardarkrushinagar).
- **B.Sc (Hons) Agriculture / Horticulture / Forestry / Fisheries (4 Years):**
  - Centralized admission via **GSAUCA** across AAU Anand, JAU Junagadh, NAU Navsari, SDAU Palanpur (**60% Board PCB + 40% GUJCET**).

---

#### 3. Group AB (Mathematics + Biology):
- **Dual Eligibility:** Students can participate in **BOTH Group A engineering/architecture counseling (ACPC) AND Group B medical/pharmacy/veterinary/agriculture counseling (ACPUGMEC/GSAUCA)**!
- **Specialized Niche Fields:** Biomedical Engineering, Biotechnology (Gujarat Biotechnology University, GIFT City), Bioinformatics, and Food/Agricultural Engineering.

---

#### 4. Major Gujarat Government Scholarships for 12th Science:
1. **MYSY (Mukhyamantri Yuva Swavalamban Yojana):**
   - **50% tuition subsidy up to ₹50,000/year** for Engineering & Pharmacy; **up to ₹2,00,000/year** for Medical (MBBS).
   - **Eligibility:** 80 percentile or higher in Class 12 Science Board, family annual income below ₹6,00,000. Plus ₹1,200/month hostel grant and book allowance.
2. **Kanya Kelavani Policy:**
   - **100% FREE Tuition Fees for all female students** in State Government Engineering and Polytechnic Colleges!
3. **TFWS (Tuition Fee Waiver Scheme):**
   - **100% Tuition Fee Exemption** for 5% supernumerary seats in every branch under ACPC counseling on merit.""")

def get_after_12th_science_group_a() -> str:
    return clean_text("""### Career & Degree Options After 12th Science Group A (PCM) in Gujarat

If you completed Class 12 Science with Mathematics (Group A), you are eligible for Gujarat's leading engineering, technology, architectural, and mathematical degree programs.

---

#### 1. B.E. / B.Tech (Engineering & Technology - 4 Years)
- **Admission Process:** Centralized counseling by **ACPC** (Admission Committee for Professional Courses).
- **Merit Rank Formula:** **50% weightage** to Class 12 Board (GSEB/CBSE) theory marks in Physics, Chemistry, and Maths + **50% weightage** to GUJCET percentile score.
- **Core Disciplines Available:**
  - **Computer Engineering / IT / AI & Data Science:** DA-IICT, Nirma, IITGN, SVNIT, LDCE, VGEC, PDEU, BVM.
  - **Chemical & Petrochemical Engineering:** Highest campus recruitment in Gujarat (Dahej PCPIR, Ankleshwar, Hazira chemical corridor). Top colleges: SVNIT, LDCE, PDEU, MSU Baroda, DDU.
  - **Electronics & Communication (ECE / VLSI):** High demand with India's Semiconductor Mission and upcoming chip fabrication plants in Sanand and Dholera.
  - **Mechanical & Automobile Engineering:** Automotive manufacturing hub in Sanand, Halol, and Rajkot. Top colleges: SVNIT, LDCE, BVM, VGEC.
  - **Civil Engineering:** Infrastructure development, Metro Rail, Dholera Smart City, Bullet Train project.
- **Seat Allocation:** 95% State Quota seats in Govt/Grant-in-Aid and 50% in Private colleges via ACPC GUJCET merit; All India seats via JEE Main.

---

#### 2. B.Arch (Bachelor of Architecture - 5 Years)
- **Eligibility & Exam:** Must pass **NATA (National Aptitude Test in Architecture)**.
- **Admission:** ACPC prepares merit list giving **50% weightage to NATA score + 50% to Class 12 Board theory marks**.
- **Top Gujarat Architecture Colleges:**
  1. **CEPT University, Ahmedabad:** Ranked amongst the best architecture institutions in India.
  2. **Faculty of Technology & Engineering, MSU Baroda:** Historic public grant-in-aid architecture faculty.
  3. **Institute of Architecture and Planning, Nirma University, Ahmedabad.**
  4. **Sarvajanik College of Engineering & Technology (SCET), Surat.**

---

#### 3. B.Plan (Bachelor of Urban & Regional Planning - 4 Years)
- Centralized admissions through ACPC based on JEE Main Paper 2 or NATA. Premier institutes: **CEPT University Ahmedabad** and **SVNIT Surat**.

---

#### 4. BCA, B.Sc IT & Data Science (3 or 4 Years NEP)
- Centralized admission via **GCAS (Gujarat Common Admission Services)** across Gujarat University, MSU Baroda, SPU, VNSGU, Saurashtra University. Ideal for software development careers without an engineering degree.

---

#### 5. Pure Sciences: B.Sc (Hons) in Mathematics / Physics / Chemistry / Statistics
- Premier colleges: St. Xavier's College (Ahmedabad), Faculty of Science (MSU Baroda), Gujarat University School of Sciences. Leads to scientific research (ISRO, PRL Ahmedabad), data analytics, and MSc/PhD.

---

#### 6. Defense, Aviation & Maritime Careers
- **National Defence Academy (NDA):** UPSC exam twice a year for 12th PCM students joining Indian Air Force or Navy.
- **Merchant Navy:** B.Tech Marine Engineering or B.Sc Nautical Science via IMU-CET.
- **Commercial Pilot License (CPL):** Flying training schools accredited by DGCA in Gujarat (GUJSAIL, AAA Ahmedabad Aviation & Aeronautics).

---

#### 7. Gujarat Financial Benefits for Group A Students:
- **MYSY Scholarship:** 50% tuition subsidy up to **₹50,000/year** for degree engineering if Board percentile is 80 or above and family income is below ₹6 LPA.
- **Kanya Kelavani Policy:** **100% Tuition Fee Exemption for ALL Girls** in Government Engineering Colleges (LDCE, VGEC, and 14 GECs)!
- **TFWS:** 100% tuition waiver for 5% supernumerary seats in every branch through ACPC.""")

def get_after_12th_science_group_b() -> str:
    return clean_text("""### Career & Degree Options After 12th Science Group B (PCB) in Gujarat

If you completed Class 12 Science with Biology (Group B), you have prestigious pathways across medical, dental, ayurvedic, homeopathic, physiotherapy, pharmacy, agriculture, and veterinary fields in Gujarat.

---

#### 1. Medical (MBBS - 5.5 Years) & Dental (BDS - 5 Years)
- **Mandatory Entrance Exam:** **NEET-UG** conducted by NTA.
- **State Counseling Body:** **ACPUGMEC** (Admission Committee for Professional Undergraduate Medical Educational Courses - medadmgujarat.org).
- **Seat Quotas:** **85% Gujarat State Quota** (reserved for Gujarat domicile/GSEB/CBSE Gujarat candidates) + 15% All India Quota.
- **Colleges in Gujarat:**
  - **6 State Government Medical Colleges (Annual Fee ~₹25,000/yr):**
    1. B.J. Medical College (BJMC), Ahmedabad (Civil Hospital) - Apex institute in Gujarat.
    2. Government Medical College (GMC), Baroda (SSG Hospital).
    3. Government Medical College (GMC), Surat (New Civil Hospital).
    4. PDU Government Medical College, Rajkot.
    5. Government Medical College, Bhavnagar.
    6. M.P. Shah Government Medical College, Jamnagar.
  - **13 GMERS Medical Colleges (Society Colleges - Govt Quota Fee ~₹3.30 Lakh/yr):** Sola (Ahmedabad), Gandhinagar, Gotri (Vadodara), Patan, Junagadh, Valsad, Himmatnagar, Vadnagar, Morbi, Porbandar, Navsari, Rajpipla, Godhra. *(MYSY reimburses up to ₹2,00,000/yr for eligible students!).*
  - **Municipal & Trust Medical Colleges:** Smt. NHL MMC Ahmedabad (SVP Hospital), SMIMER Surat, Pramukhswami Medical College Karamsad, GCS Ahmedabad.
- **Gujarat Service Bond:** 1 year compulsory rural service or penalty bond of ₹20 Lakh for Govt colleges.

---

#### 2. AYUSH Courses (BAMS & BHMS)
- **BAMS (Bachelor of Ayurvedic Medicine & Surgery - 5.5 Years):**
  - **ITRA Jamnagar (Institute of Teaching and Research in Ayurveda):** Institute of National Importance under Ministry of AYUSH.
  - Government Akhandanand Ayurved College, Ahmedabad.
  - Government Ayurved College, Vadodara.
- **BHMS (Bachelor of Homeopathic Medicine & Surgery - 5.5 Years):**
  - Government Homeopathic Medical College Dethali; Anand Homeopathic Medical College. Admissions via ACPUGMEC.

---

#### 3. Physiotherapy (BPT - 4.5 Years) & Paramedical Courses
- **Physiotherapy (BPT):** Highly popular and lucrative clinical profession in Gujarat!
- **Admission Authority:** Gujarat Paramedical Admission Committee based on **Class 12 PCB theory marks**.
- **Top Physiotherapy Colleges:** Government Physiotherapy College (Civil Hospital Ahmedabad), Government Physiotherapy College Vadodara, KM Patel Physiotherapy Karamsad.
- **Other Paramedical Programs:** B.Sc Nursing (4 yrs), GNM (3 yrs), B.Optom (Optometry at Nagar School / M&J Civil Hospital), BMLT (Medical Lab Technology).

---

#### 4. Pharmacy (B.Pharm - 4 Years & D.Pharm - 2 Years)
- **Admission Authority:** **ACPC**.
- **Merit Calculation:** **50% Board PCB theory marks + 50% GUJCET percentile**.
- **Gujarat Pharmaceutical Hub Advantage:** Gujarat manufactures over 33% of India's drugs (Zydus, Sun Pharma, Torrent, Alembic, Intas).
- **Top Pharmacy Colleges:** L.M. College of Pharmacy (LMCP Ahmedabad - Estd 1947), Institute of Pharmacy Nirma University, NIPER Ahmedabad (National Importance), B.K. Mody Government Pharmacy College Rajkot, Ramanbhai Patel College of Pharmacy (CHARUSAT Anand).

---

#### 5. Veterinary Science (B.V.Sc & A.H. - 5.5 Years)
- **Admission Authority:** **Kamdhenu University** based on **NEET-UG merit**.
- **Colleges in Gujarat:** Veterinary College Anand, Veterinary College Junagadh, Veterinary College Navsari, Veterinary College Sardarkrushinagar (Dantiwada).
- **Career Scope:** Veterinary Medical Officers (Class-II Gazetted GPSC officers), dairy cooperatives (Amul, Mother Dairy, Sumul).

---

#### 6. Agriculture & Allied Sciences (B.Sc Hons Agri - 4 Years)
- **Admission Authority:** **GSAUCA** (Gujarat State Agricultural Universities Common Admission).
- **Merit Formula:** **60% Class 12 Science PCB/PCM theory + 40% GUJCET**.
- **State Agricultural Universities:** Anand Agricultural University (AAU), Junagadh Agricultural University (JAU), Navsari Agricultural University (NAU), Sardarkrushinagar Dantiwada Agricultural University (SDAU).

---

#### 7. Financial Aid for Group B Students in Gujarat:
- **MYSY Medical Scholarship:** Reimburses **up to ₹2,00,000/year** for MBBS tuition in GMERS/Trust colleges for students with 80 percentile or above in 12th Board and income below ₹6 LPA.
- **MYSY Paramedical/Pharmacy Scholarship:** **50% tuition up to ₹50,000/year** for B.Pharm and BPT.""")

def get_after_12th_science_group_ab() -> str:
    return clean_text("""### Career & Degree Options for 12th Science Group AB (PCMB) in Gujarat

Students who opt for **Group AB (Physics, Chemistry, Mathematics, and Biology)** have the ultimate academic flexibility in Gujarat, as they satisfy the eligibility criteria for **BOTH Group A and Group B counseling bodies**.

---

#### 1. Dual Admission Eligibility:
- **Eligible for ACPC Engineering & Architecture:** Can register for B.E., B.Tech, B.Arch, and B.Plan using your Mathematics and GUJCET/JEE Main scores.
- **Eligible for ACPUGMEC Medical & Dental:** Can register for MBBS, BDS, BAMS, and BHMS using your Biology and NEET-UG scores.
- **Eligible for Gujarat Paramedical & Kamdhenu:** Can apply for BPT Physiotherapy, B.Sc Nursing, and Veterinary Science (B.V.Sc).
- **Eligible for GSAUCA Agriculture:** Can apply for B.Sc (Hons) Agriculture using either PCB or PCM scores.

---

#### 2. Unique Interdisciplinary Branches Tailor-Made for Group AB:
1. **Biomedical Engineering & Healthcare Technology:**
   - Combines human anatomy and biology with electronics and instrumentation (MRI, CT scanners, robotic surgery equipment).
   - Offered at: LDCE Ahmedabad, VGEC Chandkheda, U.V. Patel Engineering College (Ganpat Univ).
2. **Biotechnology & Bioprocess Engineering:**
   - **Gujarat Biotechnology University (GBU, GIFT City Gandhinagar):** Established in collaboration with the University of Edinburgh (UK), focused on health, industrial, and agricultural biotech.
   - Also offered at: IIT Gandhinagar, CHARUSAT Changa, Parul University.
3. **Bioinformatics & Computational Biology:**
   - Intersection of Computer Science, Data Analytics, and Genetic Sequencing.
4. **Agricultural Engineering & Food Technology:**
   - Automation of farming machinery, precision agriculture, and dairy processing (offered at AAU Anand, Kamdhenu University).

---

#### 3. Strategic Counseling Tip for Group AB Students:
- Appear for **BOTH GUJCET (for Engineering/Pharmacy) AND NEET-UG (for Medical/Veterinary)**.
- If your NEET score secures an MBBS seat via ACPUGMEC, you can accept medical admission; otherwise, you can utilize your ACPC engineering merit rank for top branches like Computer Engineering at DA-IICT, Nirma, or LDCE without losing an academic year!""")

def get_best_engineering_branches() -> str:
    branches = [
        ("Computer Engineering (CE) / IT / AI & Data Science", "Computer science and engineering", 
         "Highest campus placements across software development, cloud systems, and data analytics. Major recruitment in Gujarat across GIFT City (India's first international financial tech hub), Infocity Gandhinagar, and Ahmedabad tech corridor."),
        ("Electronics & Communication (ECE) / VLSI Design", "Electronics engineering", 
         "Explosive growth driven by India's Semiconductor Mission and upcoming mega chip fabrication facilities in Sanand and Dholera (Gujarat). High demand in embedded hardware, IoT, and telecommunications."),
        ("Chemical Engineering & Petrochemicals", "Chemical engineering", 
         "Unrivaled demand in Gujarat, which produces over 60% of India's chemicals and petrochemicals. Continuous recruitment in the Dahej PCPIR, Ankleshwar, Hazira, and Vadodara corridors (Reliance, ONGC, Deepak Nitrite, GNFC, GSFC, Atul)."),
        ("Mechanical & Automobile Engineering", "Mechanical engineering", 
         "Evergreen core discipline. Gujarat is India's leading automotive and manufacturing hub (Sanand auto corridor with Tata Motors, Halol auto hub with MG Motor, Rajkot precision engineering cluster) and central PSUs via GATE."),
        ("Civil & Structural Engineering", "Civil engineering", 
         "Prime choice for infrastructure development, high-speed rail (Mumbai-Ahmedabad Bullet Train project), Dholera Smart City, Metro rail, and state government jobs through GPSC and R&B department."),
        ("Petroleum & Energy Engineering", "Petroleum engineering", 
         "Specialized niche centered in Gandhinagar at Pandit Deendayal Energy University (PDEU) with global placements in oil, natural gas, renewable solar, and hydrogen energy (ONGC, Shell, Reliance, TotalEnergies, Adani)."),
        ("Pharmacy (B.Pharm)", "Pharmacy", 
         "Gujarat accounts for over 33% of India's pharmaceutical manufacturing (Zydus, Sun Pharma, Torrent, Alembic, Intas). Exceptional careers in formulation, clinical trials, regulatory affairs, and QC/QA.")
    ]

    out = ["### Best Engineering & Science Branches After 12th in Gujarat\n"]
    out.append("Selecting the right branch after Class 12 Science depends on your mathematics aptitude, interest in coding versus hardware/core manufacturing, and Gujarat's booming industrial landscape.\n")

    for display_name, wiki_title, scope_note in branches:
        _, ext = fetch_wiki_page(wiki_title)
        first_para = ""
        for line in ext.split("\n"):
            line = line.strip()
            if line and not line.startswith("=") and len(line.split()) >= 10:
                first_para = line
                break
        out.append(f"#### {display_name}")
        if first_para:
            out.append(f"**Academic Focus:** {first_para}")
        out.append(f"**Gujarat Industry Demand & Career Scope:** {scope_note}\n")

    out.append("#### Practical Advice on Choosing a Branch:")
    out.append("1. **Software, AI & Mathematics:** Choose Computer Engineering, IT, or Artificial Intelligence.")
    out.append("2. **Semiconductors & Hardware:** Choose ECE or VLSI Design (high government incentives in Gujarat).")
    out.append("3. **Process Chemistry & Refineries:** Choose Chemical Engineering (highest campus hiring ratio in Gujarat).")
    out.append("4. **Public Sector & Core Machinery:** Choose Mechanical or Civil for government PSU jobs (GPSC, GATE).")
    out.append("5. **College vs. Branch:** In Gujarat, Tier 1 brand value (IITGN, SVNIT, DA-IICT, Nirma) often outweighs branch variations due to stellar placement access.")

    return clean_text("\n".join(out))

def get_acpc_engineering_admission() -> str:
    return clean_text("""### Admission Procedure for ACPC Engineering in Gujarat

Undergraduate engineering admissions (B.E. / B.Tech) across government, grant-in-aid, and private universities in Gujarat are conducted by the **Admission Committee for Professional Courses (ACPC)** under the Education Department of Gujarat.

---

#### 1. Eligibility Criteria
- **Academic Stream:** Must pass Class 12 Science (Group A or Group AB) from GSEB or CBSE/ICSE schools located in Gujarat.
- **Mandatory Subjects:** Physics and Mathematics along with Chemistry / Biology / Computer / Biotechnology.
- **Minimum Qualifying Marks:** At least **45% aggregate marks** in theory PCM subjects (40% for reserved categories: SEBC/OBC, SC, ST, EWS).

---

#### 2. Composite Merit Rank Formula (100% Objective)
The ACPC state merit rank is calculated out of 100 based on:
- **50% Weightage:** Class 12 Board theory percentile in Physics, Chemistry, and Mathematics.
- **50% Weightage:** GUJCET examination percentile score.
- *Tie-breaking rules prioritize higher theory marks in Maths, followed by Physics, Chemistry, and English.*

---

#### 3. Step-by-Step ACPC Counseling Process:
1. **Online User Registration:** Register on the official ACPC portal, generate User ID and Password, and verify OTP.
2. **Document Upload:** Upload 12th marksheet, GUJCET scorecard, School Leaving Certificate, and Category/Income certificates.
3. **Provisional Merit List:** ACPC releases the common state merit rank and category ranks.
4. **Mock Round (Trial Choice Filling):** Candidates fill tentative college choices to observe simulated seat allotments and understand closing cutoff trends.
5. **Choice Filling & Locking (Round 1 & Round 2):** Fill and lock preferred colleges and branches in strict descending order of priority.
6. **Seat Allotment:** Automated seat allocation algorithm assigns seats based on state merit rank, category reservation (Open, SEBC, SC, ST, EWS, TFWS), and filled choices.
7. **Admission Confirmation & Token Fee Payment:** Pay the online token tuition fee to lock the seat and download the official ACPC Admission Allotment Slip.

---

#### 4. Seat Quota Distribution in Gujarat:
- **Government & Grant-in-Aid Colleges (LDCE, VGEC, BVM, GECs):**
  - **95% Seats:** Reserved for Gujarat candidates through ACPC GUJCET merit.
  - **5% Seats:** All India Quota filled via JEE Main score.
- **Private / Self-Financed Universities (DA-IICT, Nirma, PDEU, DDU):**
  - **50% Seats:** Filled through ACPC state merit.
  - **35% - 50% Seats:** All India Quota filled through JEE Main merit directly or via ACPC.
  - **15% Seats:** Management / NRI Quota.""")

def get_acpugmec_medical_admission() -> str:
    return clean_text("""### Medical Admissions in Gujarat (ACPUGMEC / NEET-UG)

Undergraduate medical admissions for **MBBS, BDS, BAMS (Ayurveda), and BHMS (Homeopathy)** in Gujarat are centralized through **ACPUGMEC** (Admission Committee for Professional Undergraduate Medical Educational Courses) under the Health & Family Welfare Department, Government of Gujarat.

---

#### 1. Eligibility Criteria
- **Class 12 Board:** Must pass Class 12 Science (Group B or Group AB) with Physics, Chemistry, and Biology (PCB) and English.
- **Minimum Qualifying Marks:** At least 50% aggregate in PCB (40% for SC, ST, SEBC; 45% for PwD).
- **Mandatory Entrance Exam:** **NEET-UG** conducted by the National Testing Agency (NTA). Must secure qualifying percentile in NEET.
- **Domicile:** Candidate must be an Indian citizen and have studied Class 10 & 12 in Gujarat (relaxation applies for children of Gujarat Govt / Defense employees).

---

#### 2. Seat Quotas in Gujarat Medical Colleges:
- **85% State Quota:** Administered entirely by ACPUGMEC for Gujarat domicile candidates.
- **15% All India Quota (AIQ):** Administered by Medical Counseling Committee (MCC) for government colleges.

---

#### 3. Medical College Categories & Annual Tuition Fees:
1. **6 State Government Medical Colleges (BJMC, GMC Baroda, Surat, Rajkot, Bhavnagar, Jamnagar):**
   - Annual Tuition Fee: **₹25,000 per year** (Minimal subsidized government fee).
2. **13 GMERS Medical Colleges (Society Colleges):**
   - **Government Quota Fee:** Approx **₹3,30,000 per year**. *(Eligible students under the MYSY scholarship receive reimbursement of up to ₹2,00,000 per year!).*
   - **Management Quota Fee:** Approx **₹9,00,000 per year**.
   - **NRI Quota Fee:** $22,000 per year.
3. **Municipal & Trust / Private Medical Colleges (NHL Municipal, SMIMER, Pramukhswami Karamsad, GCS):**
   - Government Quota Fee: Approx **₹6,00,000 to ₹8,50,000 per year**.
   - Management Quota: ₹16,00,000 to ₹18,00,000 per year.

---

#### 4. Mandatory Gujarat Rural Service Bond:
- Students admitted to **Government Medical Colleges** must sign a bond agreeing to serve **1 year in rural government healthcare centers** upon completion of MBBS, or pay a penalty of **₹20 Lakh**.
- For GMERS colleges, the bond commitment is 1 year rural service or ₹5 Lakh penalty.""")

def get_paramedical_admissions_gujarat() -> str:
    return clean_text("""### Paramedical & Physiotherapy Admissions in Gujarat

Paramedical healthcare professions are among the fastest-growing fields in Gujarat, offering strong hospital clinical employment right after graduation.

---

#### 1. Major Paramedical Courses After 12th Science (PCB):
- **BPT (Bachelor of Physiotherapy - 4.5 Years including 6 months internship):**
  - High demand in rehabilitation, orthopedic hospitals, sports fitness centers, and overseas licensure.
- **B.Sc Nursing (4 Years) / GNM (3 Years) / ANM (2 Years):**
  - Essential nursing roles in healthcare systems.
- **B.Optom (Bachelor of Clinical Optometry - 4 Years):**
  - Ophthalmic examination and vision care. Prestigious college: Nagar School of Optometry (Civil Hospital Ahmedabad).
- **BMLT (Bachelor of Medical Laboratory Technology - 3 Years):**
  - Diagnostic pathology, biochemistry, and microbiology labs.
- **BOT (Bachelor of Occupational Therapy - 4.5 Years):**
  - Rehabilitation for neurological and pediatric recovery.

---

#### 2. Admission Authority & Selection Process:
- Centralized admissions conducted by the **Gujarat Paramedical Admission Committee** (Committee for Admission to Physiotherapy, Nursing & Paramedical Courses).
- **Merit Rank Basis:** Prepared strictly on the basis of **Class 12 Board theory marks in Physics, Chemistry, and Biology (PCB)**. No separate entrance exam is required!
- **Scholarship Support:** Eligible students get **MYSY 50% tuition subsidy up to ₹50,000/year** for BPT and B.Sc Nursing.""")

def get_agriculture_veterinary_admissions_gujarat() -> str:
    return clean_text("""### Agriculture & Veterinary Admissions in Gujarat

Gujarat is home to world-renowned agricultural and veterinary research universities catering to the state's agrarian and cooperative dairy economy.

---

#### 1. Veterinary Science (B.V.Sc & A.H. - 5.5 Years)
- **Degree Awarded:** Bachelor of Veterinary Science and Animal Husbandry.
- **Admission Authority:** **Kamdhenu University**, Gandhinagar.
- **Selection Basis:** Strictly based on **NEET-UG examination percentile/score**.
- **Colleges in Gujarat:**
  1. College of Veterinary Science & Animal Husbandry, Anand.
  2. College of Veterinary Science & Animal Husbandry, Junagadh.
  3. College of Veterinary Science & Animal Husbandry, Navsari.
  4. College of Veterinary Science & Animal Husbandry, Sardarkrushinagar (Dantiwada).
- **Career Prospects:** Veterinary Medical Officers (GPSC Class-II Gazetted officers in Gujarat Animal Husbandry Dept), technical roles in dairy federations (Amul, Mother Dairy, NDDB, Sumul).

---

#### 2. B.Sc (Hons) Agriculture, Horticulture, Forestry & Fisheries (4 Years)
- **Admission Authority:** **GSAUCA** (Gujarat State Agricultural Universities Common Admission).
- **State Agricultural Universities:**
  1. **Anand Agricultural University (AAU), Anand.**
  2. **Junagadh Agricultural University (JAU), Junagadh.**
  3. **Navsari Agricultural University (NAU), Navsari.**
  4. **Sardarkrushinagar Dantiwada Agricultural University (SDAU), Palanpur.**
- **Merit Rank Formula:** **60% Weightage to Class 12 Science PCB/PCM theory + 40% Weightage to GUJCET score**.
- **Reservation for Farmers:** Special weightage points for sons/daughters of certified Gujarat farmers (Khedut certificate).""")

def get_d2d_admission_guidance() -> str:
    return clean_text("""### Diploma to Degree (D2D / Lateral Entry) Admission in Gujarat

Diploma to Degree (D2D) is the official lateral entry route allowing polytechnic diploma engineers to enter directly into the **2nd year (3rd semester)** of Bachelor of Engineering (B.E. / B.Tech).

---

#### 1. Eligibility Criteria
- Must have passed a 3-year Diploma in Engineering/Technology from Gujarat Technological University (GTU) or Technical Examination Board (TEB) with minimum qualifying CGPA/percentage.
- D.Pharm diploma holders can also apply for lateral entry into 2nd year B.Pharm through ACPC.

---

#### 2. Admission Authority & Quotas:
- Administered by **ACPC** through dedicated D2D online counseling.
- **Available Seats:** **10% supernumerary seats** reserved over and above approved intake in all colleges + all vacant seats from 1st-year engineering.
- **Available in All Premier Colleges:** LDCE, VGEC, BVM, MSU Baroda, Nirma, PDEU, DDU, and all 14 Government Engineering Colleges.
- **Merit Preparation:** Prepared strictly on the cumulative performance of the final two semesters (5th and 6th semester theory marks) of the diploma curriculum.""")

def get_gujcet_pattern_and_syllabus() -> str:
    return clean_text("""### GUJCET Exam Pattern & Syllabus Overview

The **Gujarat Common Entrance Test (GUJCET)** is conducted annually by GSEB for admissions into Engineering (B.E./B.Tech) and Pharmacy (B.Pharm/D.Pharm) state quota seats across Gujarat.

---

#### 1. Examination Scheme:
- **Conducting Body:** Gujarat Secondary and Higher Secondary Education Board (GSEB).
- **Mode of Exam:** Offline pen-and-paper (OMR sheet).
- **Medium of Paper:** Gujarati, English, and Hindi.
- **Total Questions:** 120 Multiple Choice Questions (MCQs).
- **Total Marks:** 120 Marks (1 mark per correct answer).
- **Negative Marking:** **0.25 marks deducted** for each incorrect response.

---

#### 2. Session Timing & Subject Structure:
1. **Session 1 (Morning - 120 Minutes / 2 Hours):**
   - **Physics:** 40 Questions (40 Marks)
   - **Chemistry:** 40 Questions (40 Marks)
   - Combined paper of 80 Questions for 80 Marks.
2. **Session 2 (Afternoon - 60 Minutes / 1 Hour):**
   - **Mathematics (Group A):** 40 Questions (40 Marks)
   - **Biology (Group B):** 40 Questions (40 Marks)

---

#### 3. Syllabus:
- Strictly covers the **GSEB / NCERT curriculum for Class 11 and Class 12 Science**:
  - **Physics:** Electrostatics, Current Electricity, Magnetism, Optics, Thermodynamics, Dual Nature, Semiconductors.
  - **Chemistry:** Solid State, Solutions, Chemical Kinetics, Coordination Compounds, Organic Haloalkanes, Alcohols, Aldehydes, Amines.
  - **Mathematics:** Matrices & Determinants, Calculus (Limits, Differentiation, Integrals), Vectors & 3D Geometry, Probability, Linear Programming.
  - **Biology:** Genetics & Evolution, Biotechnology, Human Physiology, Reproduction, Ecology & Environment.""")

def get_science_scholarships_gujarat() -> str:
    return clean_text("""### Gujarat Government Scholarships for 12th Science Students

The Government of Gujarat provides exceptional financial aid to ensure no student is deprived of professional science, engineering, or medical education due to financial constraints.

---

#### 1. MYSY (Mukhyamantri Yuva Swavalamban Yojana)
- **Benefits by Course:**
  - **Medical (MBBS / BDS):** **50% tuition subsidy up to ₹2,00,000 per year** in GMERS / Trust colleges.
  - **Engineering & Technology (B.E. / B.Tech):** **50% tuition subsidy up to ₹50,000 per year** in self-financed institutes (DA-IICT, Nirma, PDEU, DDU).
  - **Pharmacy (B.Pharm) & Physiotherapy (BPT):** **50% tuition subsidy up to ₹50,000 per year**.
  - **B.Sc / BCA Pure Science:** Up to ₹10,000 per year.
- **Hostel Assistance:** ₹1,200 per month (up to ₹12,000/year) for students staying in private hostels if government hostel is unavailable.
- **Book / Equipment Allowance:** ₹10,000 one-time for Medical; ₹5,000 for Engineering.
- **Eligibility:** Student must secure **80 percentile or above in Class 12 Science Board (GSEB/CBSE)** with annual family income below **₹6,00,000**.

---

#### 2. Kanya Kelavani Policy (Free Education for Girls)
- **Benefit:** **100% Tuition Fee Exemption** for ALL female students admitted to State Government Engineering Colleges (LDCE, VGEC, and 14 GECs) and Government Polytechnics!

---

#### 3. TFWS (Tuition Fee Waiver Scheme)
- **Benefit:** **100% Tuition Fee Waiver** for the entire 4-year degree course.
- **Seat Allocation:** 5% supernumerary seats in every branch across all ACPC technical colleges.
- **Eligibility:** Family annual income $< ₹8,00,000$; allotted strictly on ACPC merit rank.

---

#### 4. Digital Gujarat Scholarships (SC / ST / SEBC / EWS)
- **Freeship Card (SC / ST):** **100% Tuition Fee Waiver** across both government and private self-financed colleges.
- **Post-Matric Scholarship for SEBC/OBC:** Tuition fee reimbursement and hostel food bill assistance for OBC students.""")

def get_science_entrance_exams() -> str:
    return clean_text("""### Key Entrance Examinations After 12th Science in Gujarat

1. **GUJCET (Gujarat Common Entrance Test):**
   - Mandatory for Gujarat state quota (95% in Govt, 50% in Private) in B.E. / B.Tech and B.Pharm.
   - Administered by GSEB (120 marks, Class 11-12 GSEB/NCERT syllabus).
2. **NEET-UG (National Eligibility cum Entrance Test):**
   - Mandatory for all Medical (MBBS), Dental (BDS), Ayurvedic (BAMS), Homeopathic (BHMS), and Veterinary (B.V.Sc) courses in Gujarat.
3. **JEE Main (Joint Entrance Examination - Main):**
   - Compulsory for NIT Surat (SVNIT), IIIT Vadodara, IIIT Surat, and All India quota seats in Gujarat colleges (5% in Govt, 35-50% in DA-IICT, Nirma, PDEU).
4. **JEE Advanced:**
   - Mandatory for undergraduate admissions to Indian Institute of Technology Gandhinagar (IITGN).
5. **NATA (National Aptitude Test in Architecture):**
   - Mandatory for 5-year B.Arch admissions (CEPT University, MSU Baroda, Nirma) through ACPC.""")

def get_top_science_colleges_overview(domain: str = "engineering") -> str:
    if domain == "medical":
        return clean_text("""### Top Medical Colleges in Gujarat (MBBS / Healthcare)

1. **B.J. Medical College (BJMC), Ahmedabad:** Established in 1871; attached to Civil Hospital Ahmedabad. Ranked #1 in Gujarat and top 25 in India.
2. **Government Medical College (GMC), Baroda:** Attached to historic SSG Hospital in Vadodara. Renowned for clinical residency.
3. **Government Medical College (GMC), Surat:** Apex medical college in South Gujarat attached to New Civil Hospital.
4. **PDU Government Medical College, Rajkot:** Premier medical college in Saurashtra region.
5. **GMERS Medical College, Sola, Ahmedabad:** Top society medical college located on SG Highway.
6. **Smt. NHL Municipal Medical College, Ahmedabad:** Attached to state-of-the-art SVP Hospital.
7. **Pramukhswami Medical College (PSMC), Karamsad:** Premier trust medical college in Anand.""")

    elif domain == "pharmacy":
        return clean_text("""### Top Pharmacy Colleges in Gujarat (B.Pharm / M.Pharm)

1. **L.M. College of Pharmacy (LMCP), Ahmedabad:** Established in 1947, Gujarat's pioneer pharmacy college with nominal grant-in-aid fees.
2. **Institute of Pharmacy, Nirma University, Ahmedabad:** NAAC A+ accredited with advanced formulation and research laboratories.
3. **National Institute of Pharmaceutical Education and Research (NIPER), Ahmedabad:** Institute of National Importance under Ministry of Chemicals & Fertilizers.
4. **B.K. Mody Government Pharmacy College, Rajkot:** Premier government pharmacy college in Saurashtra.
5. **Ramanbhai Patel College of Pharmacy (CHARUSAT), Anand:** State-of-the-art research facilities.
6. **K.B. Institute of Pharmaceutical Education and Research (KBIPER), Gandhinagar.**""")

    # Default: Engineering
    return clean_text("""### Top Engineering & Technology Colleges in Gujarat

#### Tier 1 - National Institutes & Premier Technical Institutes:
- **IIT Gandhinagar (IITGN):** NIRF 25 (Engineering). 400-acre green campus on Sabarmati river in Palaj. Admissions via JEE Advanced.
- **SVNIT Surat:** NIRF 58. Flagship National Institute of Technology with average package of ₹11.0 LPA (CSE avg ₹15.5 LPA). Admissions via JEE Main.
- **DA-IICT Gandhinagar (Dhirubhai Ambani University):** Premier private institution for Computer Science and ICT. Average package: ₹16.5 LPA; highest: ₹54+ LPA. Admissions via JEE Main and ACPC.
- **IIIT Vadodara & IIIT Surat:** Institutes of National Importance under PPP model specializing in CSE and IT. Admissions via JEE Main.

#### Tier 2 - Premier State Government & Grant-in-Aid Colleges:
- **L.D. College of Engineering (LDCE), Ahmedabad:** Flagship state government college (Estd 1948). Nominal government fee (₹1,500/year for boys, 100% Free for girls) and strong campus placements (avg ₹6.5-7.0 LPA).
- **Vishwakarma Government Engineering College (VGEC), Chandkheda, Ahmedabad:** Located adjacent to GTU headquarters; highly popular for Computer Engineering.
- **Birla Vishvakarma Mahavidyalaya (BVM), Anand:** Gujarat's first engineering college (Estd 1948). Autonomous grant-in-aid institution.
- **Faculty of Technology & Engineering, MSU Baroda:** Historic public engineering faculty with deep industrial ties.
- **IITRAM Ahmedabad:** Autonomous state government institute focusing on infrastructure engineering.

#### Tier 2 - Leading Private Universities:
- **Nirma University (Institute of Technology), Ahmedabad:** NAAC A+ accredited 115-acre campus on SG Highway. Average package: ₹8.5-9.5 LPA for CSE.
- **Pandit Deendayal Energy University (PDEU), Gandhinagar:** 100-acre campus near GIFT City with top infrastructure for Energy, Chemical, and Computer Engineering.
- **Ahmedabad University (SEAS), Ahmedabad:** Progressive interdisciplinary curriculum.
- **DDU Nadiad & CHARUSAT Anand:** Highly reputed engineering campuses in central Gujarat.""")

def get_fees_and_scholarships(college: dict = None, query: str = "") -> str:
    if college:
        out = [
            f"### Fee Structure & Scholarships: {college['name']}\n",
            f"- **Institution Type:** {college['type']}",
            f"- **Annual Fees:** {college.get('fees', 'Refer to official ACPC brochure.')}",
            f"- **Average Placement Package:** {college.get('avg_package', 'N/A')}\n",
            "#### Applicable Gujarat Government Scholarships:",
            "1. **MYSY (Mukhyamantri Yuva Swavalamban Yojana):**",
            "   - **50% tuition subsidy up to ₹50,000/year** for Engineering/Pharmacy; **up to ₹2,00,000/year** for Medical (MBBS).",
            "   - Eligibility: Class 12 Science Board percentile 80 or above, family annual income below ₹6 Lakh.",
            "2. **Kanya Kelavani Policy:**",
            "   - **100% FREE Tuition Fees for all female students** in State Government Engineering and Polytechnic Colleges!",
            "3. **TFWS (Tuition Fee Waiver Scheme):**",
            "   - **100% Tuition Fee Exemption** for 5% supernumerary seats in every branch under ACPC counseling on merit."
        ]
        return clean_text("\n".join(out))

    q_lower = query.lower()
    if any(k in q_lower for k in ["medical", "mbbs", "bds", "doctor", "hospital"]):
        return clean_text("""### Fee Structure for Medical Colleges in Gujarat (MBBS)

#### 1. State Government Medical Colleges (BJMC Ahmedabad, GMC Baroda, Surat, Rajkot, Bhavnagar, Jamnagar):
- **Annual Tuition Fee:** Nominal **₹25,000 per year** (Govt subsidized fee). Hostel: ~₹2,000/year.
- **Rural Service Bond:** 1 year mandatory rural healthcare service or ₹20 Lakh penalty.

#### 2. GMERS Medical Colleges (13 Semi-Government / Society Colleges across Gujarat):
- **Government Quota Fee:** Approx **₹3,30,000 per year**.
  *(Under MYSY, eligible students with 80+ percentile receive reimbursement of up to ₹2,00,000/year, bringing net tuition down to ₹1,30,000/year!).*
- **Management Quota Fee:** Approx **₹9,00,000 per year**.
- **NRI Quota Fee:** $22,000 per year.
- **Rural Service Bond:** 1 year rural service or ₹5 Lakh penalty.

#### 3. Municipal & Trust Medical Colleges (NHL MMC Ahmedabad, SMIMER Surat, Pramukhswami Karamsad):
- **Government Quota Fee:** Approx **₹6,00,000 to ₹8,50,000 per year** (Eligible for MYSY up to ₹2 Lakh).
- **Management Quota Fee:** Approx **₹16,00,000 to ₹18,50,000 per year**.""")

    if any(k in q_lower for k in ["engineering", "b.tech", "btech", "b.e", "be"]):
        return clean_text("""### Fee Structure for Engineering Colleges in Gujarat (B.E. / B.Tech)

#### 1. State Government Engineering Colleges (LDCE, VGEC, and 14 GECs):
- **Tuition Fee for Boys:** Nominal **₹1,500 per year** (₹750 per semester).
- **Tuition Fee for Girls:** **100% FREE (₹0 Tuition Fee)** under Gujarat Government's **Kanya Kelavani Policy**!
- **Hostel Fee:** Approx ₹2,000 - ₹3,000 per year.

#### 2. Grant-in-Aid Engineering Colleges (BVM Anand, MSU Baroda):
- **Tuition Fee:** Highly subsidized, approx **₹3,000 - ₹5,000 per year**.

#### 3. Premier Autonomous & Private Universities:
- **DA-IICT Gandhinagar:** Approx **₹2,20,000 - ₹2,40,000 per year**.
- **Nirma University (ITNU):** Approx **₹2,15,000 - ₹2,30,000 per year**.
- **PDEU Gandhinagar:** Approx **₹2,55,000 - ₹2,65,000 per year**.
- **Ahmedabad University (SEAS):** Approx **₹3,00,000 per year**.
- **LJ University / Silver Oak / Indus:** Approx **₹78,000 - ₹1,15,000 per year**.

#### Financial Subsidies:
- **MYSY:** Reimburses 50% tuition up to **₹50,000/year** for degree engineering students with 80+ percentile in 12th Board.
- **TFWS:** **100% Tuition Fee Exemption** for 5% supernumerary merit seats in every branch.""")

    return get_science_scholarships_gujarat()

def get_low_marks_guidance() -> str:
    return clean_text("""### Career & Degree Pathways for Low Marks in 12th Science (Gujarat)

Securing a lower percentile or modest marks in 12th Science does NOT close doors to successful careers in Gujarat. There are multiple high-value pathways:

---

#### 1. Group A (Mathematics) Low Marks Options:
1. **BCA & B.Sc (IT / Data Science / Computer Science):**
   - Centralized admission via **GCAS (Gujarat Common Admission Services)** across state universities (Gujarat University, MSU Baroda, SPU, VNSGU).
   - High industry recruitment in Ahmedabad & GIFT City for software development without requiring high engineering cutoff ranks.
2. **Diploma to Degree (D2D) Lateral Route:**
   - Complete a 3-year Polytechnic Diploma, score well in the final 5th/6th semesters, and enter directly into the 2nd year of top engineering colleges (LDCE, VGEC, BVM) via ACPC!
3. **Private Engineering Colleges Vacant Quota:**
   - ACPC conducts vacant seat rounds where self-financed engineering colleges admit students based on minimum passing criteria.
4. **Defense & Maritime Careers:**
   - Indian Air Force / Navy technical trades, Merchant Navy via IMU-CET (B.Sc Nautical Science).

---

#### 2. Group B (Biology) Low Marks Options:
1. **B.Sc Nursing (4 Years) & GNM (3 Years):**
   - Strong clinical demand with guaranteed placements across Gujarat civil and corporate hospitals (Apollo, Zydus, CIMS).
2. **Paramedical Science Programs:**
   - Bachelor of Physiotherapy (BPT self-financed colleges), Medical Lab Technology (BMLT), Radiology/Imaging, and Optometry.
3. **Pure & Applied Life Sciences via GCAS:**
   - B.Sc in Biotechnology, Microbiology, Biochemistry, or Chemistry leading to high recruitment in Gujarat's massive pharmaceutical manufacturing hub (Zydus, Sun Pharma, Torrent, Alembic).
4. **Agriculture & Allied Courses:**
   - Self-financed agriculture and horticulture colleges affiliated with state universities.""")

def get_gujcet_compulsory_clarification() -> str:
    return clean_text("""### Is GUJCET Compulsory for Higher Education in Gujarat?

The rule depends on whether you are applying for **State Quota seats** or **All India Quota seats**:

---

#### 1. Where GUJCET is 100% Mandatory:
- **State Quota in Government Colleges (LDCE, VGEC, 14 GECs):**
  - **95% of total seats** are allotted strictly through ACPC using the Gujarat merit formula: **50% Board PCM Theory + 50% GUJCET percentile**.
- **State Quota in Private Universities (DA-IICT, Nirma, PDEU, DDU):**
  - **50% of total seats** are filled through ACPC state merit based on GUJCET.
- **B.Pharm & D.Pharm State Quota:**
  - 100% of ACPC state quota seats require GUJCET (PCB or PCM).
- **GSAUCA Agriculture Universities (AAU, JAU, NAU, SDAU):**
  - **40% weightage** is strictly calculated from your GUJCET score.

---

#### 2. Where You Can Get Admission WITHOUT GUJCET:
1. **National Institutes in Gujarat:**
   - **IIT Gandhinagar (IITGN):** Strictly requires **JEE Advanced**.
   - **SVNIT Surat, IIIT Vadodara, IIIT Surat:** Require **JEE Main** via JoSAA/CSAB counseling.
2. **All India Quota in State Colleges via ACPC:**
   - **5% seats** in Government Engineering Colleges are reserved for All India candidates through **JEE Main score**.
3. **All India Quota in Top Private Universities:**
   - **DA-IICT Gandhinagar:** 35% - 50% seats filled directly via **JEE Main**.
   - **Nirma University:** 35% seats filled directly via **JEE Main**.
   - **PDEU Gandhinagar:** 50% seats filled directly via **JEE Main**.
   - **Ahmedabad University (SEAS) & Adani University:** Allot seats on JEE Main merit.""")

def get_jee_main_colleges_gujarat() -> str:
    return clean_text("""### Colleges & Quotas Accepting JEE Main in Gujarat

Students can use their **JEE Main score** to secure engineering admissions in Gujarat across three tiers:

---

#### 1. National Institutes (Centralized JoSAA / CSAB Counseling):
1. **SVNIT Surat (Sardar Vallabhbhai National Institute of Technology):** Flagship NIT with Home State & Other State quotas via JEE Main.
2. **IIIT Vadodara & IIIT Surat:** Institutes of National Importance under PPP model offering CSE and IT via JEE Main.

#### 2. Premier Private Universities (Dedicated JEE Main All India Quota):
1. **DA-IICT Gandhinagar:** 35% to 50% seats filled via JEE Main (cutoff ~98.5+ percentile for ICT/MnC).
2. **Nirma University (Institute of Technology), Ahmedabad:** 35% All India seats via JEE Main (cutoff ~96-97 percentile for CSE).
3. **PDEU Gandhinagar:** 50% All India seats allotted through JEE Main rank.
4. **Ahmedabad University (SEAS):** Evaluates JEE Main scores for B.Tech admission.
5. **IITRAM Ahmedabad:** 50% seats filled through JEE Main merit via ACPC / CSAB.
6. **Adani University & Indus University:** Accept JEE Main rank for direct engineering seats.

#### 3. State Government Engineering Colleges (5% All India Quota via ACPC):
- **LDCE Ahmedabad, VGEC Chandkheda, BVM Anand, and all 14 GECs** reserve **5% of their total seats** for candidates applying through JEE Main via ACPC counseling!""")

def get_placements_and_packages(college: dict = None) -> str:
    if college:
        out = [
            f"### Placements & Packages: {college['name']}\n",
            f"- **Average Placement CTC:** **{college.get('avg_package', 'N/A')}**",
            f"- **Highest Placement CTC:** **{college.get('highest_package', 'N/A')}**",
            f"- **Top Recruiters:** {', '.join(college.get('top_recruiters', ['Leading technology & healthcare organizations']))}",
            f"- **Cutoff & Admission Route:** {college.get('cutoffs', 'Admissions via ACPC / National Entrance')}\n",
            f"#### Overview & Highlights:",
            f"{college.get('overview', '')}"
        ]
        return clean_text("\n".join(out))

    return clean_text("""### Placement Packages Across Top Gujarat Science & Engineering Colleges

- **DA-IICT Gandhinagar:** Average Package: **₹16.5 LPA** | Highest: **₹54+ LPA (Domestic) / ₹1.2+ Crore (International)**. Recruiters: Google, Microsoft, Amazon, Atlassian.
- **IIT Gandhinagar (IITGN):** Average Package: **₹15.5 LPA** | Highest: **₹62 LPA**. Recruiters: Texas Instruments, Google, Amazon, Adani.
- **IIIT Vadodara & IIIT Surat:** Average Package: **₹12.5 - ₹13.5 LPA** | Highest: **₹43 LPA**. Recruiters: Adobe, Amazon, MathWorks, Siemens.
- **SVNIT Surat:** Average Package: **₹11.0 LPA** (CSE avg ~₹15.5 LPA) | Highest: **₹52 LPA**. Recruiters: Microsoft, Samsung, L&T, Reliance.
- **Nirma University (Institute of Technology):** Average Package: **₹8.5 - ₹9.5 LPA** (CSE) | Highest: **₹46 LPA**. Recruiters: Morgan Stanley, Oracle, Amazon.
- **Pandit Deendayal Energy University (PDEU):** Average Package: **₹7.5 - ₹8.5 LPA** | Highest: **₹42 LPA**. Recruiters: ONGC, Shell, Reliance, Total.
- **L.D. College of Engineering (LDCE):** Average Package: **₹6.5 - ₹7.0 LPA** (Unbeatable ROI with ₹1,500/year fee). Highest: **₹22 LPA**.""")

def get_cutoffs_and_merits(college: dict = None, query: str = "") -> str:
    if college:
        out = [
            f"### Admission Cutoffs & Merit Ranks: {college['name']}\n",
            f"- **Entrance Exams:** {', '.join(college.get('exams', ['GUJCET', 'JEE Main']))}",
            f"- **Cutoff / Closing Rank Trends:** {college.get('cutoffs', 'Refer to official ACPC portal.')}",
            f"- **Annual Fees:** {college.get('fees', 'Refer to official brochure.')}",
            f"- **Average Package:** {college.get('avg_package', 'N/A')}\n",
            "#### Gujarat ACPC Merit Formula (Engineering):",
            "- **50% Weightage:** Class 12 Board theory percentile in Physics, Chemistry, and Mathematics.",
            "- **50% Weightage:** GUJCET Examination percentile."
        ]
        return clean_text("\n".join(out))

    q_lower = query.lower()
    if any(k in q_lower for k in ["medical", "mbbs", "bds", "neet", "doctor"]):
        return clean_text("""### Medical (MBBS / BDS) NEET-UG Cutoffs in Gujarat (85% State Quota)

#### 1. State Government Medical Colleges (NEET-UG Closing Score Trends):
1. **B.J. Medical College (BJMC), Ahmedabad:** NEET Score **645 - 670+** (General Merit Rank Top 150)
2. **Government Medical College (GMC), Baroda:** NEET Score **625 - 650+**
3. **Government Medical College (GMC), Surat:** NEET Score **615 - 640+**
4. **PDU Government Medical College, Rajkot:** NEET Score **605 - 630+**
5. **Government Medical College, Bhavnagar:** NEET Score **595 - 620+**
6. **M.P. Shah Government Medical College, Jamnagar:** NEET Score **590 - 615+**

#### 2. GMERS Medical Colleges (Government Quota in Society Colleges):
- **GMERS Sola, Gandhinagar, Gotri, Himmatnagar, etc.:** NEET Score **560 - 610+** (Eligible for MYSY scholarship up to ₹2 Lakh/year!).

#### 3. Municipal & Trust Medical Colleges (NHL Municipal, SMIMER):
- **Government Quota:** NEET Score **550 - 595+**
- **Management Quota:** NEET Score **480 - 540+**""")

    return clean_text("""### Gujarat Science Admission Cutoffs & Merit Benchmarks

#### 1. Computer Engineering (Open Category ACPC Closing Ranks):
1. **DA-IICT Gandhinagar (ICT / MnC):** ACPC Rank **150 - 250** (JEE Main 98.5+ percentile)
2. **Nirma University (CSE):** ACPC Rank **350 - 550** (JEE Main 96-97 percentile)
3. **L.D. College of Engineering (LDCE CE):** ACPC Rank **500 - 800**
4. **DDU Nadiad (Grant-in-Aid CE):** ACPC Rank **700 - 1,200**
5. **VGEC Chandkheda (CE):** ACPC Rank **1,000 - 1,500**
6. **BVM Anand (CE):** ACPC Rank **1,200 - 2,000**
7. **PDEU Gandhinagar (CE):** ACPC Rank **800 - 1,500**
8. **MSU Baroda (CSE):** ACPC Rank **1,000 - 1,800**
9. **GEC Gandhinagar (CE):** ACPC Rank **2,500 - 4,000**

#### 2. Medical (MBBS NEET-UG State Quota Cutoffs in Gujarat):
1. **B.J. Medical College (BJMC), Ahmedabad:** NEET Score **640 - 665+**
2. **Government Medical College (GMC), Baroda:** NEET Score **620 - 645+**
3. **Government Medical College (GMC), Surat:** NEET Score **615 - 640+**
4. **GMERS Medical Colleges (Government Quota):** NEET Score **580 - 615+**""")

def compare_science_colleges(query: str) -> str:
    q_lower = query.lower()
    c1, c2 = None, None

    if "daiict" in q_lower or "da-iict" in q_lower:
        c1 = next((c for c in INSTITUTIONS if c.get("id") == "daiict"), None)
    if "nirma" in q_lower:
        c2 = next((c for c in INSTITUTIONS if c.get("id") == "nirma"), None)

    if not c1 or not c2:
        if "iit" in q_lower and "svnit" in q_lower:
            c1 = next((c for c in INSTITUTIONS if c.get("id") == "iitgn"), None)
            c2 = next((c for c in INSTITUTIONS if c.get("id") == "svnit"), None)
        elif "ldce" in q_lower and "vgec" in q_lower:
            c1 = next((c for c in INSTITUTIONS if c.get("id") == "ldce"), None)
            c2 = next((c for c in INSTITUTIONS if c.get("id") == "vgec"), None)
        elif "bjmc" in q_lower and ("baroda" in q_lower or "gmc" in q_lower):
            c1 = next((c for c in INSTITUTIONS if c.get("id") == "bjmc"), None)
            c2 = next((c for c in INSTITUTIONS if c.get("id") == "gmc_baroda"), None)

    if not c1 or not c2:
        found = []
        for c in INSTITUTIONS:
            if c.get("name", "").lower() in q_lower or c.get("id", "") in q_lower:
                found.append(c)
                if len(found) == 2:
                    break
        if len(found) == 2:
            c1, c2 = found[0], found[1]

    if c1 and c2:
        out = [
            f"### Comprehensive Comparison: {c1['name']} vs. {c2['name']}\n",
            f"| Metric | {c1['name']} | {c2['name']} |",
            f"| :--- | :--- | :--- |",
            f"| **Location** | {c1.get('city')} | {c2.get('city')} |",
            f"| **Type** | {c1.get('type')} | {c2.get('type')} |",
            f"| **Average Package / Clinical Stipend** | **{c1.get('avg_package', 'N/A')}** | **{c2.get('avg_package', 'N/A')}** |",
            f"| **Highest Package** | **{c1.get('highest_package', 'N/A')}** | **{c2.get('highest_package', 'N/A')}** |",
            f"| **Annual Fees** | {c1.get('fees', 'N/A')} | {c2.get('fees', 'N/A')} |",
            f"| **Cutoff Trends** | {c1.get('cutoffs', 'N/A')} | {c2.get('cutoffs', 'N/A')} |",
            f"| **Exams Accepted** | {', '.join(c1.get('exams', []))} | {', '.join(c2.get('exams', []))} |\n",
            "#### Analysis & Recommendation:",
            f"- **Choose {c1['name']} if:** You seek {c1.get('avg_package', 'specialized')} outcomes, focused research, and established faculty.",
            f"- **Choose {c2['name']} if:** You prefer broader multi-disciplinary exposure, strong state alumni network, or location convenience."
        ]
        return clean_text("\n".join(out))

    return clean_text("""### Science College Comparison in Gujarat

When comparing science and engineering colleges in Gujarat, key decision points include:
1. **Government ROI vs. Private Infrastructure:** Government colleges like LDCE and VGEC charge only ₹1,500/year (100% Free for girls) providing unmatched ROI; private colleges (DA-IICT, Nirma, PDEU) charge ~₹2.2L - ₹2.6L/year but offer ultra-modern infrastructure and higher corporate placement packages.
2. **DA-IICT vs. Nirma:** DA-IICT is the undisputed leader for Computer Science / ICT with ₹16.5 LPA average package; Nirma offers robust ₹8.5-9.5 LPA average for CSE with a larger 115-acre campus.
3. **IITGN vs. SVNIT:** IITGN offers interdisciplinary project-based curriculum on the Sabarmati river in Palaj; SVNIT Surat is an established NIT with immense core engineering industry recruitment.""")

def format_college_profile(college: dict, query: str) -> str:
    t, ext = fetch_wiki_page(college["name"])
    out = [
        f"### {college['name']}\n",
        f"- **Location:** {college.get('city')}",
        f"- **Institution Type:** {college.get('type')}",
        f"- **Category:** {college.get('category', 'Science & Technology').title()}",
        f"- **NIRF / Recognition:** {college.get('nirf_rank')}",
        f"- **Annual Fees:** {college.get('fees')}",
        f"- **Placement Stats / Stipend:** Average {college.get('avg_package', 'N/A')} | Highest {college.get('highest_package', 'N/A')}",
        f"- **Exams Accepted:** {', '.join(college.get('exams', []))}\n",
        "#### Overview & Specific Details:"
    ]
    if ext:
        extracted = extractive_sentence_qa(query, ext)
        out.append(extracted if extracted else college.get("overview", ""))
    else:
        out.append(college.get("overview", ""))
    return clean_text("\n".join(out))

def get_welcome_greeting() -> str:
    return clean_text("""### 👋 Welcome to GujaratEdu!

Hii! Welcome to **GujaratEdu Higher Education Advisory**.

You can ask any questions related to **higher studies and admissions after 12th Science in Gujarat** (Group A - PCM, Group B - PCB, and Group AB - PCMB):

* **Courses & Degrees:** B.E. / B.Tech engineering branches, MBBS, BDS, B.Pharm, B.Sc (Agriculture, IT, Pure Sciences), Physiotherapy (BPT), Nursing, etc.
* **Admissions & Merit:** ACPC engineering & pharmacy counseling, ACPUGMEC medical admissions, GUJCET weightage, and JEE Main seats in Gujarat.
* **Colleges & Universities:** DA-IICT, Nirma, LDCE, VGEC, IIT Gandhinagar, SVNIT, PDPU, MSU Baroda, BJ Medical, GMERS, and top private universities.
* **Fees & Scholarships:** Government vs. SFI private college fees, MYSY (₹2,00,000 / ₹50,000 subsidy), Kanya Kelavani (Free education for girls), and TFWS quota.
* **Cutoffs & Career Guidance:** Closing merit ranks, guidance for low marks/percentile, and branch comparisons.

💬 **How can I help you today?** Type your question below (for example: *"Top engineering colleges in Ahmedabad"* or *"MBBS government college fees"*).
""")

# ==============================================================================
# MASTER QUERY ROUTER (12th SCIENCE ONLY - GUJARAT ONLY)
# ==============================================================================

def answer_query(query: str) -> str:
    clean_q = query.strip()
    if not clean_q:
        return "Please ask a question regarding higher education after 12th Science in Gujarat."

    q_lower = clean_q.lower()

    # 0. Greetings & Welcome Handler
    if re.search(r'^(?:hi+|hey+|hello+|hlo+|namaste|kem\s*cho|kemcho|good\s*(?:morning|afternoon|evening)|greetings?)(?:\s+(?:there|bot|sir|madam|all|gujaratedu))?[!?,.\s]*$', q_lower) or \
       re.search(r'^(?:who are you|what can you do|how are you|how can you help|help me)[!?,.\s]*$', q_lower):
        return get_welcome_greeting()

    # 1. Dynamic Multi-Criteria Institution Filter & Listing
    # (e.g., "Give me the names of private university of ahemdabad for btech", "Government engineering colleges in Ahmedabad")
    filter_result = parse_and_filter_institutions(clean_q)
    if filter_result:
        return filter_result

    # 2. Colleges Accepting JEE Main
    if re.search(r'\b(jee main.*colleges?|colleges?.*jee main|accept.*jee main|jee main seats?)\b', q_lower):
        return get_jee_main_colleges_gujarat()

    # 3. Is GUJCET Compulsory / Without GUJCET
    if re.search(r'\b(is gujcet (?:compulsory|mandatory|required)|without gujcet|admission without gujcet|can i get.*without gujcet)\b', q_lower):
        return get_gujcet_compulsory_clarification()

    # 4. Low marks / Low percentile options
    if re.search(r'\b(low marks?|low percentile|less marks?|average marks?|bad marks?|poor marks?|failed in neet|low rank)\b', q_lower):
        return get_low_marks_guidance()

    # 5. Detect specific science college
    college = find_science_college(clean_q)

    # 6. Fees & Scholarships
    if re.search(r'\b(fees?|fee structure|costs?|tuitions?|scholarships?|mysy|tfws|kanya kelavani|free education|financial aid)\b', q_lower):
        return get_fees_and_scholarships(college, query=clean_q)

    # 7. Placements & Packages
    if re.search(r'\b(placements?|packages?|highest package|average package|salaries|salary|recruiters?|stipends?)\b', q_lower):
        return get_placements_and_packages(college)

    # 8. Cutoffs & Merit Rank
    if re.search(r'\b(cutoffs?|cut off|closing ranks?|merit ranks?|how many marks|percentile needed|can i get|marks needed)\b', q_lower):
        return get_cutoffs_and_merits(college, query=clean_q)

    # 9. College Comparison (e.g. DA-IICT vs Nirma, IITGN vs SVNIT, LDCE vs VGEC)
    if re.search(r'\b(vs\.?|versus|better|compare|comparison|difference between)\b', q_lower):
        return compare_science_colleges(clean_q)

    # 10. Direct College Profile (e.g., "Tell me about BJMC", "Tell me about DA-IICT", "About Nirma")
    if college and any(k in q_lower for k in ["tell me about", "overview", "about", "details", "information", "who is", "where is", "history", "campus", "profile"]):
        return format_college_profile(college, clean_q)

    # 11. D2D / Lateral Entry (Diploma to Degree)
    if re.search(r'\b(d2d|diploma to degree|lateral entry|polytechnic to degree|diploma to b\.?e|diploma to b\.?tech)\b', q_lower):
        return get_d2d_admission_guidance()

    # 12. Paramedical / Physiotherapy (BPT) / Nursing
    if re.search(r'\b(paramedical|physiotherapy|bpt|nursings?|b\.sc nursing|gnm|anm|optometry|bmlt)\b', q_lower):
        return get_paramedical_admissions_gujarat()

    # 13. Medical / MBBS / BDS / AYUSH / ACPUGMEC
    if re.search(r'\b(acpugmec|medadmgujarat|mbbs|bds|bams|bhms|ayush|medical colleges?|medical admissions?|admissions? in mbbs|doctor.*after 12)\b', q_lower):
        if "college" in q_lower or "list" in q_lower:
            return get_top_science_colleges_overview("medical")
        return get_acpugmec_medical_admission()

    # 14. Agriculture / Veterinary / GSAUCA / Kamdhenu
    if re.search(r'\b(gsauca|agriculture|agricultural|kamdhenu|veterinary|b\.v\.sc|dairy technology|horticulture|fisheries)\b', q_lower):
        return get_agriculture_veterinary_admissions_gujarat()

    # 15. Entrance Exams for 12th Science in Gujarat
    if re.search(r'\b(entrance exams?|exams?.*after 12|which entrance exam|which exams?.*after 12|exams? for science|exams? for engineering|exams? for medical)\b', q_lower):
        return get_science_entrance_exams()

    # 16. Specific Science Groups: Group AB, Group A, Group B
    if re.search(r'\b(group ab|group-ab|group a&b|group a and b|pcmb)\b', q_lower):
        return get_after_12th_science_group_ab()

    if re.search(r'\b(group a|group-a|pcm\b|maths.*science|science.*maths|options.*group a|after 12.*group a|career.*group a)\b', q_lower):
        return get_after_12th_science_group_a()

    if re.search(r'\b(group b|group-b|pcb\b|biology.*science|science.*biology|options.*group b|after 12.*group b|career.*group b)\b', q_lower):
        return get_after_12th_science_group_b()

    # 17. Best Branches / Branch Comparison (supports typos like 'brach')
    if (re.search(r'\bbran?ch(?:es)?\b', q_lower) and re.search(r'\b(best|good|scope|top|which|choose|recommend|future|compare)\b', q_lower)) or \
       re.search(r'\b(best\s+(?:engineering\s+)?bran?ch(?:es)?|which\s+(?:engineering\s+)?bran?ch(?:es)?|choose\s+bran?ch|bran?ch(?:es)?\s+.*best|scope of|engineering bran?ch(?:es)?)\b', q_lower):
        return get_best_engineering_branches()

    # 18. GUJCET Pattern & Syllabus
    if re.search(r'\b(gujcet syllabus|gujcet pattern|marking scheme|exam format|exam pattern|syllabus of gujcet|pattern of gujcet)\b', q_lower):
        return get_gujcet_pattern_and_syllabus()

    # 19. ACPC Admission Process
    if "acpc" in q_lower or ("admission" in q_lower and "process" in q_lower) or ("admission" in q_lower and "procedure" in q_lower) or ("engineering" in q_lower and "admission" in q_lower) or ("admission in engineering" in q_lower):
        return get_acpc_engineering_admission()

    # 20. General "after 12th science" or "options after 12th" in Gujarat
    if re.search(r'\b(after 12|courses? after 12|options? after 12|what after 12|what to do after 12|higher education.*after 12|career.*after 12|science field|career options?)\b', q_lower):
        return get_after_12th_science_overview()

    # 21. Top Science Colleges / Rankings in Gujarat
    if re.search(r'\b(top|best)\b', q_lower) and re.search(r'\b(colleges?|universit(?:y|ies)|institutes?)\b', q_lower):
        if "pharmacy" in q_lower or "b.pharm" in q_lower:
            return get_top_science_colleges_overview("pharmacy")
        elif "medical" in q_lower or "mbbs" in q_lower:
            return get_top_science_colleges_overview("medical")
        return get_top_science_colleges_overview("engineering")

    # 22. Individual College Lookup (Fallback if college name provided directly)
    if college:
        return format_college_profile(college, clean_q)

    # 23. External Search API Integration (if user configured an API key)
    api_result = query_search_api(clean_q)
    if api_result:
        return clean_text(f"### Relevant Gujarat Higher Education Results\n\n{api_result}")

    # 24. Wikipedia Extractive Fallback with Educational Guardrails
    results = search_wiki(clean_q, limit=3)
    if results:
        target_title = results[0]
        t, ext = fetch_wiki_page(target_title)
        if ext:
            extracted = extractive_sentence_qa(clean_q, ext)
            return clean_text(f"### {t}\n\n{extracted}")

    return "Could not find specific Gujarat higher education information matching your query. Please ask about 12th Science courses (Group A, Group B, Group AB), engineering/medical cutoffs, ACPC/ACPUGMEC admissions, fees, or scholarships in Gujarat."

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:]).strip()
        print(answer_query(query))
    else:
        print("=" * 65)
        print("  Gujarat Higher Education QA Bot: After 12th Science")
        print("=" * 65)
        print("Type your question below (or 'exit' to quit):\n")
        while True:
            try:
                q = input("Ask a question > ").strip()
                if not q:
                    continue
                if q.lower() in ["exit", "quit", "q"]:
                    print("Exiting bot.")
                    break
                print("\n" + answer_query(q) + "\n")
                print("-" * 65)
            except (KeyboardInterrupt, EOFError):
                print("\nExiting bot.")
                break
