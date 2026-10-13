import streamlit as st
import sqlite3
import datetime
import json
import random

# ==================== DATABASE & SRS ENGINE ====================
DB_NAME = "hsk4_app.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY DEFAULT 1,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            streak INTEGER DEFAULT 0,
            last_login_date TEXT,
            hearts INTEGER DEFAULT 3,
            max_hearts INTEGER DEFAULT 3,
            hsk4_exam_date TEXT
        )
    ''')
    c.execute("SELECT COUNT(*) FROM user_stats")
    if c.fetchone()[0] == 0:
        today = datetime.date.today().isoformat()
        exam_date = (datetime.date.today() + datetime.timedelta(days=180)).isoformat()
        c.execute('''
            INSERT INTO user_stats (id, xp, level, streak, last_login_date, hearts, max_hearts, hsk4_exam_date)
            VALUES (1, 0, 1, 1, ?, 3, 3, ?)
        ''', (today, exam_date))
        
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocab_deck (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            sample_zh TEXT,
            sample_pinyin TEXT,
            sample_en TEXT,
            category TEXT DEFAULT 'HSK4 Official',
            context_note TEXT,
            repetitions INTEGER DEFAULT 0,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            next_review_date TEXT,
            last_reviewed_date TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS grammar_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            structure_pattern TEXT NOT NULL,
            english_meaning TEXT NOT NULL,
            tokens_json TEXT NOT NULL,
            correct_order_json TEXT NOT NULL,
            full_sentence TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            grammar_explanation TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS custom_word_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            context_note TEXT,
            date_added TEXT
        )
    ''')
    conn.commit()
    conn.close()

def load_user_stats():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT xp, level, streak, last_login_date, hearts, max_hearts, hsk4_exam_date FROM user_stats WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return {"xp": 0, "level": 1, "streak": 1, "hearts": 3, "max_hearts": 3, "exam_date": ""}
    
    today = datetime.date.today()
    last_login = datetime.date.fromisoformat(row[3]) if row[3] else today
    streak = row[2]
    
    if today > last_login:
        if (today - last_login).days == 1:
            streak += 1
        elif (today - last_login).days > 1:
            streak = 1
        
        conn = get_connection()
        c2 = conn.cursor()
        c2.execute("UPDATE user_stats SET streak = ?, last_login_date = ? WHERE id = 1", (streak, today.isoformat()))
        conn.commit()
        conn.close()

    return {
        "xp": row[0],
        "level": row[1],
        "streak": streak,
        "last_login_date": row[3],
        "hearts": row[4],
        "max_hearts": row[5],
        "exam_date": row[6]
    }

def add_xp(amount):
    stats = load_user_stats()
    current_xp = stats["xp"] + amount
    new_level = 1 + (current_xp // 100)
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE user_stats SET xp = ?, level = ? WHERE id = 1", (current_xp, new_level))
    conn.commit()
    conn.close()
    return current_xp, new_level, (new_level > stats["level"])

def update_hearts(delta):
    stats = load_user_stats()
    new_hearts = max(0, min(stats["max_hearts"], stats["hearts"] + delta))
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE user_stats SET hearts = ? WHERE id = 1", (new_hearts,))
    conn.commit()
    conn.close()
    return new_hearts

def reset_hearts():
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE user_stats SET hearts = max_hearts WHERE id = 1")
    conn.commit()
    conn.close()

def calculate_sm2(quality, repetitions, interval, ease_factor):
    if quality >= 2:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = int(interval * ease_factor)
        repetitions += 1
    else:
        repetitions = 0
        interval = 1

    ease_factor = ease_factor + (0.1 - (3 - quality) * (0.08 + (3 - quality) * 0.02))
    if ease_factor < 1.3:
        ease_factor = 1.3
    return repetitions, interval, ease_factor

def review_card(card_id, quality):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT repetitions, interval, ease_factor FROM vocab_deck WHERE id = ?", (card_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    reps, interval, ef = row
    new_reps, new_interval, new_ef = calculate_sm2(quality, reps, interval, ef)
    today = datetime.date.today()
    next_review = today + datetime.timedelta(days=new_interval)
    c.execute('''
        UPDATE vocab_deck
        SET repetitions = ?, interval = ?, ease_factor = ?, last_reviewed_date = ?, next_review_date = ?
        WHERE id = ?
    ''', (new_reps, new_interval, new_ef, today.isoformat(), next_review.isoformat(), card_id))
    conn.commit()
    conn.close()

def get_due_cards(limit=15):
    today = datetime.date.today().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT id, word_hanzi, pinyin, english, sample_zh, sample_pinyin, sample_en, category, context_note
        FROM vocab_deck
        WHERE next_review_date IS NULL OR next_review_date <= ?
        ORDER BY RANDOM()
        LIMIT ?
    ''', (today, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_deck_stats():
    conn = get_connection()
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    c.execute("SELECT COUNT(*) FROM vocab_deck")
    total_cards = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vocab_deck WHERE next_review_date IS NULL OR next_review_date <= ?", (today,))
    due_cards = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vocab_deck WHERE category = 'Daily Conversation'")
    custom_cards = c.fetchone()[0]
    conn.close()
    return {"total": total_cards, "due": due_cards, "custom": custom_cards}

# ==================== DATASET SEEDING ====================
OFFICIAL_HSK4_VOCAB = [
    ("爱情", "àiqíng", "Love / Romance", "真正的爱情需要互相理解。", "Zhēnzhèng de àiqíng xūyào hùxiāng lǐjiě.", "True love requires mutual understanding."),
    ("安排", "ānpái", "To arrange / Plan", "经理安排了明天的会议。", "Jīnglǐ ānpáile míngtiān de huìyì.", "The manager arranged tomorrow's meeting."),
    ("按时", "ànshí", "On time / Punctually", "请按时完成这份工作。", "Qǐng ànshí wánchéng zhè fèn gōngzuò.", "Please finish this work on time."),
    ("按照", "ànzhào", "According to", "按照规定，这里不能停车。", "Ànzhào guīdìng, zhèlǐ bùnéng tíngchē.", "According to regulations, parking is not allowed here."),
    ("抱歉", "bàoqiàn", "Apologetic / Feel sorry", "非常抱歉，我迟到了。", "Fēicháng bàoqiàn, wǒ chídào le.", "I'm very sorry I'm late."),
    ("保证", "bǎozhèng", "To guarantee / Ensure", "我保证明天按时交作业。", "Wǒ bǎozhèng míngtiān ànshí jiāo zuòyè.", "I guarantee to submit my homework on time tomorrow."),
    ("本来", "běnlái", "Originally / At first", "我本来打算今天去跑步。", "Wǒ běnlái dǎsuàn jīntiān qù pǎobù.", "I originally intended to go running today."),
    ("比如", "bǐrú", "For example / Such as", "有些水果很甜，比如西瓜。", "Yǒuxiē shuǐguǒ hěn tián, bǐrú xīguā.", "Some fruits are very sweet, for example watermelon."),
    ("毕业", "bìyè", "To graduate", "他明年大学毕业。", "Tā míngnián dàxué bìyè.", "He graduates from university next year."),
    ("表格", "biǎogé", "Form / Table / Spreadsheet", "请填写这张表格。", "Qǐng tiánxiě zhè zhāng biǎogé.", "Please fill out this form."),
    ("并且", "bìngqiě", "And / Furthermore / Also", "他聪明并且很谦虚。", "Tā cōngmíng bìngqiě hěn qiānxū.", "He is smart and also humble."),
    ("不过", "búguò", "However / But", "这件衣服好看，不过有点贵。", "Zhè jiàn yīfu hǎokàn, búguò yǒudiǎn guì.", "This clothing looks good, but is a bit expensive."),
    ("不得不", "bùdébù", "To have to / Cannot but", "天气太热，我不得不开空调。", "Tiānqì tài rè, wǒ bùdébù kāi kōngtiáo.", "The weather is too hot, I have to turn on the AC."),
    ("不管", "bùguǎn", "No matter / Regardless of", "不管天气怎样，我都要去。", "Bùguǎn tiānqì zěnyàng, wǒ dōu yào qù.", "No matter the weather, I will go."),
    ("不仅", "bùjǐn", "Not only", "他不仅聪明，而且很努力。", "Tā bùjǐn cōngmíng, érqiě hěn nǔlì.", "He is not only smart, but also hardworking."),
    ("擦", "cā", "To wipe / Rub / Clean", "请把桌子擦干净。", "Qǐng bǎ zhuōzi cā gānjìng.", "Please wipe the table clean."),
    ("猜", "cāi", "To guess", "你能猜出来他是谁吗？", "Nǐ néng cāi chūlái tā shì shéi ma?", "Can you guess who he is?"),
    ("材料", "cáiliào", "Material / Document", "准备好开会的材料了吗？", "Zhǔnbèi hǎo kāihuì de cáiliào le ma?", "Are the meeting materials ready?"),
    ("差不多", "chàbuduō", "Almost / About the same", "两个人的答案差不多。", "Liǎng gè rén de dá'àn chàbuduō.", "The two answers are almost the same."),
    ("成功", "chénggōng", "Success / To succeed", "经过努力，他成功了。", "Jīngguò nǔlì, tā chénggōng le.", "Through effort, he succeeded."),
    ("重新", "chóngxīn", "Anew / Again", "我们重新开始做这项工作。", "Wǒmen chóngxīn kāishǐ zuò zhè xiàng gōngzuò.", "Let's start this work anew."),
    ("到底", "dàodǐ", "What on earth / In the end", "你到底选择哪一个？", "Nǐ dàodǐ xuǎnzé nǎ yí gè?", "Which one do you choose in the end?"),
    ("随着", "suízhe", "Along with / As", "随着科技的发展，生活更方便了。", "Suízhe kēxué de fāzhǎn, shēnghuó gèng fāngbiàn le.", "Along with tech development, life is more convenient.")
]

GRAMMAR_CHALLENGES = [
    {
        "title": "Structure 1: 把 Sentence with Result Complement",
        "structure_pattern": "Subject + 把 + Object + Verb + Result/Complement",
        "english_meaning": "Please wipe the table clean.",
        "tokens": ["把", "桌子", "擦干净", "请", "你"],
        "correct_order": ["请", "你", "把", "桌子", "擦干净"],
        "full_sentence": "请你把桌子擦干净。",
        "pinyin": "Qǐng nǐ bǎ zhuōzi cā gānjìng.",
        "grammar_explanation": "The 把 (bǎ) construction shifts the object before the action verb to show an action resulting in a state change."
    },
    {
        "title": "Structure 2: Not only... but also (不仅...而且...)",
        "structure_pattern": "Subject + 不仅 + Verb1/Adj1 + 而且 + Verb2/Adj2",
        "english_meaning": "He is not only smart, but also very hardworking.",
        "tokens": ["而且", "他", "很努力", "不仅", "聪明"],
        "correct_order": ["他", "不仅", "聪明", "而且", "很努力"],
        "full_sentence": "他不仅聪明，而且很努力。",
        "pinyin": "Tā bùjǐn cōngmíng, érqiě hěn nǔlì.",
        "grammar_explanation": "不仅 (bùjǐn) ... 而且 (érqiě) connects two progressive clauses emphasizing multiple positive attributes."
    },
    {
        "title": "Structure 3: Passive Voice 被 Construction",
        "structure_pattern": "Object + 被 + Agent + Verb + Result",
        "english_meaning": "My bicycle was ridden away by him.",
        "tokens": ["骑走了", "我的", "自行车", "被", "他"],
        "correct_order": ["我的", "自行车", "被", "他", "骑走了"],
        "full_sentence": "我的自行车被他骑走了。",
        "pinyin": "Wǒ de zìxíngchē bèi tā qí zǒu le.",
        "grammar_explanation": "The 被 (bèi) construction places the recipient of the action first, creating a passive structure."
    }
]

def seed_database():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vocab_deck WHERE category = 'HSK4 Official'")
    if c.fetchone()[0] == 0:
        today = datetime.date.today().isoformat()
        for item in OFFICIAL_HSK4_VOCAB:
            c.execute('''
                INSERT INTO vocab_deck (word_hanzi, pinyin, english, sample_zh, sample_pinyin, sample_en, category, ease_factor, next_review_date)
                VALUES (?, ?, ?, ?, ?, ?, 'HSK4 Official', 2.5, ?)
            ''', (item[0], item[1], item[2], item[3], item[4], item[5], today))
            
    c.execute("SELECT COUNT(*) FROM grammar_challenges")
    if c.fetchone()[0] == 0:
        for g in GRAMMAR_CHALLENGES:
            c.execute('''
                INSERT INTO grammar_challenges (title, structure_pattern, english_meaning, tokens_json, correct_order_json, full_sentence, pinyin, grammar_explanation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (g["title"], g["structure_pattern"], g["english_meaning"], json.dumps(g["tokens"]), json.dumps(g["correct_order"]), g["full_sentence"], g["pinyin"], g["grammar_explanation"]))
    conn.commit()
    conn.close()

# ==================== STREAMLIT UI ====================
st.set_page_config(page_title="HSK3 → HSK4 Gamified App", page_icon="🐉", layout="wide")
init_db()
seed_database()

st.markdown("""
<style>
    .main-title { font-size: 2.2rem; font-weight: 800; background: linear-gradient(90deg, #FF4B4B, #FF8533, #FFC300); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .stat-card { background-color: #1E222A; border-radius: 12px; padding: 12px; text-align: center; border: 1px solid #333948; }
    .stat-val { font-size: 1.5rem; font-weight: bold; color: #FFC300; }
    .flashcard { background: linear-gradient(135deg, #2A2F3D, #1F232D); border: 2px solid #FF8533; border-radius: 16px; padding: 30px; text-align: center; }
    .hanzi-display { font-size: 3.5rem; font-weight: bold; color: #FFF; }
    .pinyin-display { font-size: 1.5rem; color: #FF8533; }
</style>
""", unsafe_allow_html=True)

user_stats = load_user_stats()
deck_stats = get_deck_stats()
exam_date_obj = datetime.date.fromisoformat(user_stats["exam_date"]) if user_stats["exam_date"] else (datetime.date.today() + datetime.timedelta(days=180))
days_left = (exam_date_obj - datetime.date.today()).days

st.markdown('<div class="main-title">🐉 HSK3 → HSK4 Gamified Trainer</div>', unsafe_allow_html=True)
st.caption(f"Target Exam Date: <b>{exam_date_obj.strftime('%B %d, %Y')}</b> ({days_left} Days Remaining)", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
with m1: st.markdown(f'''<div class="stat-card"><div class="stat-val">⭐ Lvl {user_stats["level"]}</div><div>{user_stats["xp"]} XP</div></div>''', unsafe_allow_html=True)
with m2: st.markdown(f'''<div class="stat-card"><div class="stat-val">🔥 {user_stats["streak"]} Days</div><div>Daily Streak</div></div>''', unsafe_allow_html=True)
with m3: st.markdown(f'''<div class="stat-card"><div class="stat-val">{"❤️"*user_stats["hearts"]}</div><div>Health Pool</div></div>''', unsafe_allow_html=True)
with m4: st.markdown(f'''<div class="stat-card"><div class="stat-val">🎴 {deck_stats["due"]} / {deck_stats["total"]}</div><div>SRS Cards Due</div></div>''', unsafe_allow_html=True)

st.write("---")

tab1, tab2, tab3, tab4 = st.tabs(["🎴 SRS Flashcards", "🧩 Grammar Builder", "📝 Daily Word Capture", "⚡ Speed Quiz"])

# --- TAB 1: SRS FLASHCARDS ---
with tab1:
    due_cards = get_due_cards(limit=10)
    if not due_cards:
        st.success("🎉 All due cards reviewed! Great job!")
    else:
        if "s_idx" not in st.session_state: st.session_state.s_idx = 0
        if "show_ans" not in st.session_state: st.session_state.show_ans = False
        
        card = due_cards[st.session_state.s_idx % len(due_cards)]
        cid, hz, py, en, szh, spy, sen, cat, note = card
        
        st.markdown(f'''
        <div class="flashcard">
            <div class="hanzi-display">{hz}</div>
            <div class="pinyin-display">{py}</div>
        ''', unsafe_allow_html=True)
        
        if st.session_state.show_ans:
            st.markdown(f"<div style='font-size:1.3rem; margin-top:15px;'>💡 {en}</div>", unsafe_allow_html=True)
            if szh: st.info(f"Example: {szh} ({spy}) - '{sen}'")
        st.markdown('</div>', unsafe_allow_html=True)
        
        if not st.session_state.show_ans:
            if st.button("👀 Reveal Answer", use_container_width=True):
                st.session_state.show_ans = True
                st.rerun()
        else:
            r1, r2, r3, r4 = st.columns(4)
            with r1:
                if st.button("🔴 Again", use_container_width=True):
                    review_card(cid, 0)
                    st.session_state.show_ans = False
                    st.session_state.s_idx += 1
                    st.rerun()
            with r2:
                if st.button("🟠 Hard", use_container_width=True):
                    review_card(cid, 1); add_xp(5)
                    st.session_state.show_ans = False
                    st.session_state.s_idx += 1
                    st.rerun()
            with r3:
                if st.button("🟢 Good", use_container_width=True):
                    review_card(cid, 2); add_xp(10)
                    st.session_state.show_ans = False
                    st.session_state.s_idx += 1
                    st.rerun()
            with r4:
                if st.button("🌟 Easy", use_container_width=True):
                    review_card(cid, 3); add_xp(15)
                    st.session_state.show_ans = False
                    st.session_state.s_idx += 1
                    st.rerun()

# --- TAB 2: GRAMMAR BUILDER ---
with tab2:
    st.subheader("🧩 Sentence Assembly Challenge")
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT title, english_meaning, tokens_json, correct_order_json, grammar_explanation FROM grammar_challenges")
    ch_rows = c.fetchall(); conn.close()
    
    if "g_i" not in st.session_state: st.session_state.g_i = 0
    if "user_seq" not in st.session_state: st.session_state.user_seq = []
    
    ch = ch_rows[st.session_state.g_i % len(ch_rows)]
    g_title, g_en, tokens_json, correct_json, expl = ch
    tokens = json.loads(tokens_json); correct_order = json.loads(correct_json)
    
    st.markdown(f"#### Target: *\"{g_en}\"*")
    st.markdown(f"**Your Assembly:** `{' '.join(st.session_state.user_seq)}`")
    
    unplaced = [t for t in tokens if st.session_state.user_seq.count(t) < tokens.count(t)]
    cols = st.columns(len(unplaced) if unplaced else 1)
    for idx, t in enumerate(unplaced):
        if cols[idx].button(f"➕ {t}", key=f"t_{idx}_{t}"):
            st.session_state.user_seq.append(t)
            st.rerun()
            
    if st.button("✅ Submit Order"):
        if st.session_state.user_seq == correct_order:
            st.success("🎉 Correct Word Order!")
            add_xp(25)
        else:
            st.error(f"❌ Incorrect! Correct order: {' '.join(correct_order)}")
            update_hearts(-1)
        st.info(f"💡 Rule: {expl}")
        
    if st.button("🔄 Clear / Next"):
        st.session_state.user_seq = []
        st.session_state.g_i += 1
        st.rerun()

# --- TAB 3: DAILY WORD CAPTURE ---
with tab3:
    st.subheader("📝 Capture Real-World Words")
    with st.form("add_w"):
        f_hz = st.text_input("Hanzi*")
        f_py = st.text_input("Pinyin*")
        f_en = st.text_input("English*")
        f_note = st.text_input("Context Note")
        if st.form_submit_button("➕ Save to SRS Deck"):
            if f_hz and f_py and f_en:
                conn = get_connection(); c = conn.cursor()
                today = datetime.date.today().isoformat()
                c.execute("INSERT INTO vocab_deck (word_hanzi, pinyin, english, category, context_note, next_review_date) VALUES (?, ?, ?, 'Daily Conversation', ?, ?)", (f_hz, f_py, f_en, f_note, today))
                conn.commit(); conn.close()
                add_xp(15)
                st.success(f"Saved '{f_hz}' to SRS deck!")
                st.rerun()

# --- TAB 4: SPEED QUIZ ---
with tab4:
    st.subheader("⚡ Speed Run Quiz")
    if st.button("🚀 Start Quiz"):
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT word_hanzi, english FROM vocab_deck ORDER BY RANDOM() LIMIT 5")
        q_data = c.fetchall(); conn.close()
        st.session_state.q_set = q_data
        st.rerun()
        
    if "q_set" in st.session_state:
        for idx, q in enumerate(st.session_state.q_set):
            st.markdown(f"**Q{idx+1}:** What does **{q[0]}** mean?")
            st.write(f"Meaning: {q[1]}")
        if st.button("Finish Quiz (+20 XP)"):
            add_xp(20)
            st.balloons()
            st.success("Quiz Completed! Earned +20 XP")
