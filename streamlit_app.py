# streamlit_app.py
import math
import random
from typing import Dict, List, Tuple, Any
from datetime import date, timedelta
import json

import pandas as pd
import streamlit as st

st.set_page_config(page_title="CoC6 能力値振りツール", layout="wide", initial_sidebar_state="expanded")

# =========================
# 定数・ユーティリティ（共通）
# =========================
ABILS = ["STR", "CON", "POW", "DEX", "APP", "SIZ", "INT", "EDU"]
DERIVED_KEYS = ["HP", "MP", "SAN", "アイデア", "幸運", "知識", "職業P", "興味P"]
ALL_KEYS_FOR_RULE = ABILS + DERIVED_KEYS + ["TOTAL"]

ROLL_SPEC = {  # (UI表記, 固定加算)
    "STR": ("3d6", 0),  "CON": ("3d6", 0),  "POW": ("3d6", 0),
    "DEX": ("3d6", 0),  "APP": ("3d6", 0),
    "SIZ": ("2d6+6", 6), "INT": ("2d6+6", 6), "EDU": ("3d6+3", 3),
}

WARN_MIN = {k: 3 for k in ABILS}
WARN_MAX = {k: 18 for k in ABILS}  # 警告のみ（ブロックしない）

def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))

def roll_nd6(n: int) -> Tuple[int, List[int]]:
    dice = [random.randint(1, 6) for _ in range(n)]
    return sum(dice), dice

def roll_for(stat: str) -> Tuple[int, List[int], int]:
    """戻り: (素の合計=出目合計+固定加算, 出目配列, 固定加算)"""
    spec, add = ROLL_SPEC[stat]
    if spec.startswith("3d6"):
        s, dice = roll_nd6(3)
    elif spec.startswith("2d6"):
        s, dice = roll_nd6(2)
    else:
        raise ValueError("Unknown dice spec")
    return s + add, dice, add

def damage_bonus(str_val: int, siz_val: int) -> str:
    total = str_val + siz_val
    if 2 <= total <= 12:  return "-1D6"
    if 13 <= total <= 16: return "-1D4"
    if 17 <= total <= 24: return "+0"
    if 25 <= total <= 32: return "+1D4"
    if 33 <= total <= 40: return "+1D6"
    if total < 2:        return "-1D6"
    extra = (total - 33) // 8
    return f"+{extra+1}D6"

def derived_stats(stats: Dict[str, int]) -> Dict[str, int]:
    CON = stats["CON"]; SIZ = stats["SIZ"]; POW = stats["POW"]; INT = stats["INT"]; EDU = stats["EDU"]
    HP = round_half_up((CON + SIZ) / 2)
    return {
        "HP": HP, "MP": POW, "SAN": POW * 5,
        "アイデア": INT * 5, "幸運": POW * 5, "知識": EDU * 5,
        "職業P": EDU * 20, "興味P": INT * 10,
    }

def total_score(stats: Dict[str, int]) -> int:
    return sum(stats[a] for a in ABILS)

# =========================
# プロフィール用データ
# =========================
PREFECTURES = [
    "北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬","埼玉","千葉","東京","神奈川",
    "新潟","富山","石川","福井","山梨","長野","岐阜","静岡","愛知","三重","滋賀","京都","大阪","兵庫",
    "奈良","和歌山","鳥取","島根","岡山","広島","山口","徳島","香川","愛媛","高知","福岡","佐賀","長崎",
    "熊本","大分","宮崎","鹿児島","沖縄"
]
WORLD_COUNTRIES = [
    "United States","United Kingdom","Canada","Australia","New Zealand","Germany","France","Italy","Spain","Portugal",
    "Netherlands","Belgium","Sweden","Norway","Denmark","Finland","Poland","Czech Republic","Austria","Switzerland",
    "Ireland","Greece","Hungary","Romania","Bulgaria","Serbia","Croatia","Slovakia","Slovenia","Ukraine",
    "Russia","Turkey","Saudi Arabia","UAE","Qatar","India","Pakistan","Bangladesh","Sri Lanka","Nepal",
    "China","Taiwan","South Korea","Thailand","Vietnam","Malaysia","Singapore","Indonesia","Philippines","Mexico",
    "Brazil","Argentina","Chile","Peru","Colombia","South Africa","Egypt","Kenya","Nigeria","Morocco"
]
JOBS_JP = [
    "学生","会社員","公務員","教員","エンジニア","研究者","医師","看護師","弁護士","警察官","自営業",
    "農家","漁師","記者","作家","芸術家","俳優","ミュージシャン","料理人","探偵","通訳","パイロット","整備士"
]
JOBS_WORLD = [
    "Student","Office worker","Civil servant","Teacher","Engineer","Scientist","Doctor","Nurse","Lawyer","Police officer",
    "Entrepreneur","Farmer","Fisher","Journalist","Writer","Artist","Actor","Musician","Chef","Detective","Interpreter",
    "Pilot","Mechanic"
]

def random_date(ymin: int, ymax: int) -> date:
    start = date(ymin, 1, 1)
    end   = date(ymax, 12, 31)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))

# =========================
# セッション初期化（1度だけ）
# =========================
if "app_bootstrap_done" not in st.session_state:
    # タブ1（能力値）
    st.session_state.current_stats  = {a: 0 for a in ABILS}
    st.session_state.current_base   = {a: 0 for a in ABILS}
    st.session_state.current_detail = {a: [] for a in ABILS}
    st.session_state.current_add    = {a: 0 for a in ABILS}
    st.session_state.modifiers      = {a: 0 for a in ABILS}
    st.session_state.fixed_values   = {a: None for a in ABILS}
    st.session_state.history        = []
    st.session_state.favorites      = []
    st.session_state.auto_fav_enabled = True
    st.session_state.auto_fav_mode    = "AND"
    st.session_state.auto_min         = {k: None for k in ALL_KEYS_FOR_RULE}
    st.session_state.auto_max         = {k: None for k in ALL_KEYS_FOR_RULE}
    st.session_state.history_max_keep   = 20
    st.session_state.add_roll_to_history= True

    # タブ2（プロフィール）
    st.session_state.profile_history = []

    st.session_state.app_bootstrap_done = True

# =========================
# タブ
# =========================
tab1, tab2 = st.tabs(["🧮 能力値ツール", "🪪 プロフィール生成"])

# =========================
# タブ1：能力値ツール
# =========================
with tab1:
    st.title("STATUS　　　ALL（全能力を振る）")

    apply_mod = st.toggle(
        "モディファイアを最終値に適用する",
        value=True,
        help="OFFで最終値にモディファイアを加算しません（素の合計のみ）。ONで最終値に加算します。"
    )

    def make_final(abil: str, base_val: int) -> int:
        return base_val + (st.session_state.modifiers[abil] if apply_mod else 0)

    def make_record(finals: Dict[str, int],
                    base_vals: Dict[str, int],
                    detail: Dict[str, List[int]],
                    adds: Dict[str, int]) -> Dict[str, Any]:
        rec = {
            **finals,
            "TOTAL": total_score(finals),
            **derived_stats(finals),
            "_base": base_vals, "_detail": detail, "_adds": adds,
            "_mods": dict(st.session_state.modifiers),
            "_apply_mod": apply_mod,
        }
        return rec

    def auto_fav_ok(rec: Dict[str, Any]) -> bool:
        if not st.session_state.auto_fav_enabled:
            return False
        flags: List[bool] = []
        for k in ALL_KEYS_FOR_RULE:
            v = int(rec[k])
            vmin = st.session_state.auto_min.get(k)
            vmax = st.session_state.auto_max.get(k)
            if (vmin is not None) or (vmax is not None):
                ok = True
                if vmin is not None: ok = ok and (v >= int(vmin))
                if vmax is not None: ok = ok and (v <= int(vmax))
                flags.append(ok)
        if not flags:
            return False
        return all(flags) if st.session_state.auto_fav_mode == "AND" else any(flags)

    # ---- サイドバー（タブ1専用） ----
    with st.sidebar:
        st.title("操作パネル（能力値）")

        # フォーム：まとめて振る
        with st.form("batch_roll_form", clear_on_submit=False):
            st.subheader("まとめて振る（履歴に追加）")
            n_sets = st.number_input("セット数（最大5）", min_value=1, max_value=5, value=1, step=1, key="batch_n_sets")

            st.markdown("**固定値の指定**（空=未指定）")
            cols_fix = st.columns(4)
            for i, abil in enumerate(ABILS):
                with cols_fix[i % 4]:
                    v = st.number_input(f"{abil} 固定", min_value=0, max_value=99,
                                        value=st.session_state.fixed_values[abil] or 0, step=1, key=f"fix_{abil}")
                    st.session_state.fixed_values[abil] = v if v != 0 else None

            st.markdown("**モディファイア（±）**")
            cols_mod = st.columns(4)
            for i, abil in enumerate(ABILS):
                with cols_mod[i % 4]:
                    st.session_state.modifiers[abil] = st.number_input(
                        f"{abil} 加算/減算", min_value=-30, max_value=30,
                        value=st.session_state.modifiers[abil], step=1, key=f"mod_{abil}"
                    )

            submitted = st.form_submit_button("まとめて振る（履歴に追加）", use_container_width=True)
            if submitted:
                newrecs = []
                for _ in range(int(n_sets)):
                    base_vals, finals, detail, adds = {}, {}, {}, {}
                    for abil in ABILS:
                        fixed = st.session_state.fixed_values[abil]
                        if fixed is not None:
                            base = fixed; d = []; add = 0
                        else:
                            base, d, add = roll_for(abil)
                        base_vals[abil] = base
                        detail[abil] = d
                        adds[abil] = add
                        finals[abil] = make_final(abil, base)
                    rec = make_record(finals, base_vals, detail, adds)
                    newrecs.append(rec)

                # まとめて前置 → トリム
                st.session_state.history[:0] = newrecs
                maxk = max(5, int(st.session_state.history_max_keep))
                if len(st.session_state.history) > maxk:
                    del st.session_state.history[maxk:]

                # 自動★
                favs = [r for r in newrecs if auto_fav_ok(r)]
                if favs:
                    st.session_state.favorites[:0] = favs

                st.success(f"{len(newrecs)} セットを履歴に追加（★ {len(favs)} 件）")

        st.markdown("---")
        st.subheader("履歴・★ 設定")
        st.session_state.history_max_keep = st.number_input("履歴の最大保持数", min_value=5, max_value=200, value=20, step=1)
        st.checkbox("全体ロールを履歴に保存する", value=st.session_state.add_roll_to_history, key="add_roll_to_history")

        st.checkbox("自動お気に入りを有効化", value=st.session_state.auto_fav_enabled, key="auto_fav_enabled")
        st.radio("条件の結合", options=["AND", "OR"],
                 index=0 if st.session_state.auto_fav_mode=="AND" else 1,
                 key="auto_fav_mode", horizontal=True)

        st.caption("自動お気に入りの範囲条件（下限/上限）。空=0で未指定。対象：全能力・全派生・TOTAL")
        cond_df = pd.DataFrame({
            "項目": ALL_KEYS_FOR_RULE,
            "下限": [st.session_state.auto_min[k] or 0 for k in ALL_KEYS_FOR_RULE],
            "上限": [st.session_state.auto_max[k] or 0 for k in ALL_KEYS_FOR_RULE],
        })
        edited_cond = st.data_editor(cond_df, use_container_width=True, num_rows="固定", key="auto_cond_table")
        for _, row in edited_cond.iterrows():
            k = row["項目"]
            lo = int(row["下限"]) if int(row["下限"]) != 0 else None
            hi = int(row["上限"]) if int(row["上限"]) != 0 else None
            st.session_state.auto_min[k] = lo
            st.session_state.auto_max[k] = hi

    # ---- 全能力を振る（履歴に保存オプション）----
    def roll_all_into_current(save_to_history: bool):
        base_vals, finals, detail, adds = {}, {}, {}, {}
        for abil in ABILS:
            fixed = st.session_state.fixed_values[abil]
            if fixed is not None:
                base = fixed; d = []; add = 0
            else:
                base, d, add = roll_for(abil)
            st.session_state.current_base[abil]   = base
            st.session_state.current_detail[abil] = d
            st.session_state.current_add[abil]    = add
            final_val = make_final(abil, base)
            st.session_state.current_stats[abil]  = final_val

            base_vals[abil] = base
            finals[abil]    = final_val
            detail[abil]    = d
            adds[abil]      = add

        if save_to_history:
            rec = make_record(finals, base_vals, detail, adds)
            st.session_state.history.insert(0, rec)
            maxk = max(5, int(st.session_state.history_max_keep))
            if len(st.session_state.history) > maxk:
                del st.session_state.history[maxk:]
            if auto_fav_ok(rec):
                st.session_state.favorites.insert(0, rec)

    b1, b3 = st.columns([1,2])
    with b1:
        if st.button("🎲 全能力を振る", use_container_width=True):
            roll_all_into_current(st.session_state.add_roll_to_history)
            st.success("現在セットを新規ロールしました。")
    with b3:
        st.caption("固定あり→固定値／固定なし→ダイス。履歴保存はトグルでON/OFF。最終値はモディファイア設定に従う。")

    st.markdown("---")

    # ---- 能力一覧（横並び）＋ TOTAL（EDUの右）----
    st.subheader("能力一覧（横並び）")

    def cb_reroll_one(abil: str):
        fixed = st.session_state.fixed_values.get(abil)
        if fixed is not None:
            base = fixed; d = []; add = 0
        else:
            base, d, add = roll_for(abil)
        st.session_state.current_base[abil]   = base
        st.session_state.current_detail[abil] = d
        st.session_state.current_add[abil]    = add
        st.session_state.current_stats[abil]  = make_final(abil, base)

    cols = st.columns(len(ABILS) + 1)
    for i, abil in enumerate(ABILS):
        with cols[i]:
            st.markdown(f"### {abil}  \n<small>{ROLL_SPEC[abil][0]}</small>", unsafe_allow_html=True)
            detail = st.session_state.current_detail.get(abil, [])
            add = st.session_state.current_add.get(abil, 0)
            if detail:
                st.text(f"出目: [{', '.join(map(str, detail))}]" + (f" +{add}" if add else ""))
            else:
                st.text("出目: - (" + ("固定" if st.session_state.fixed_values.get(abil) is not None else "未振り") + ")")
            base_val = st.session_state.current_base.get(abil, 0)
            final_val = st.session_state.current_stats.get(abil, 0)
            st.text(f"素の合計: {base_val}")
            st.metric("最終値", final_val, help="モディファイア適用後（トグルでON/OFF）")
            st.button("🎲", key=f"reroll_{abil}", help=f"{abil} を振り直す",
                      use_container_width=True, on_click=cb_reroll_one, args=(abil,))

    with cols[-1]:
        finals_now = {a: st.session_state.current_stats[a] for a in ABILS}
        st.markdown("### TOTAL  \n<small>sum of abilities</small>", unsafe_allow_html=True)
        st.metric("合計", total_score(finals_now))

    st.markdown("---")

    # ---- 派生ステータス ----
    st.subheader("派生ステータス")
    finals_now = {a: st.session_state.current_stats[a] for a in ABILS}
    deriv = derived_stats(finals_now)
    db = damage_bonus(finals_now["STR"], finals_now["SIZ"])

    cA, cB, cC, cD = st.columns(4)
    with cA:
        st.metric("HP", deriv["HP"])
        st.metric("MP", deriv["MP"])
    with cB:
        st.metric("SAN", deriv["SAN"])
        st.metric("幸運", deriv["幸運"])
    with cC:
        st.metric("アイデア", deriv["アイデア"])
        st.metric("知識", deriv["知識"])
    with cD:
        st.metric("職業P", deriv["職業P"])
        st.metric("興味P", deriv["興味P"])
    st.info(f"ダメージボーナス（STR+SIZ={finals_now['STR']+finals_now['SIZ']}）：**{db}**")

    st.markdown("---")

    # ---- スワップ / xポイント移動 ----
    st.subheader("出目入れ替え（スワップ） / xポイント移動")

    def swap(a: str, b: str):
        cs = st.session_state.current_stats
        cb_ = st.session_state.current_base
        cd = st.session_state.current_detail
        ca = st.session_state.current_add
        cs[a], cs[b]   = cs[b], cs[a]
        cb_[a], cb_[b] = cb_[b], cb_[a]
        cd[a], cd[b]   = cd[b], cd[a]
        ca[a], ca[b]   = ca[b], ca[a]

    def move_points(from_a: str, to_b: str, x: int):
        st.session_state.current_stats[from_a] -= x
        st.session_state.current_stats[to_b]   += x

    c1, c2, c3, c4 = st.columns([1,1,1,1])
    with c1:
        swap_a = st.selectbox("入れ替え元", ABILS, index=0)
    with c2:
        swap_b = st.selectbox("入れ替え先", ABILS, index=1)
    with c3:
        move_from = st.selectbox("減らす能力", ABILS, index=0)
    with c4:
        move_to   = st.selectbox("増やす能力", ABILS, index=1)

    c5, c6 = st.columns(2)
    with c5:
        if st.button("↔ 入れ替える", use_container_width=True):
            swap(swap_a, swap_b)
            st.success(f"{swap_a} と {swap_b} を入れ替えました。")
    with c6:
        move_x = st.number_input("移動ポイント", min_value=1, max_value=50, value=1, step=1)
        if st.button("➕➖ 移動を実行", use_container_width=True):
            move_points(move_from, move_to, int(move_x))
            st.info(f"{move_from} -{move_x} / {move_to} +{move_x}（合計不変）")

    # 範囲警告（素の合計で評価）
    warns = []
    for k in ABILS:
        v = st.session_state.current_base.get(k, 0)
        if v < WARN_MIN[k] or v > WARN_MAX[k]:
            warns.append(f"{k} が範囲外（素の合計 {v} / 推奨 {WARN_MIN[k]}〜{WARN_MAX[k]}）")
    if warns:
        st.warning(" / ".join(warns))

    st.markdown("---")

    # ---- 履歴（並べ替え・採用・★チェック）----
    with st.expander("履歴（並べ替え・採用・★チェック）", expanded=False):
        if st.session_state.history:
            sort_key = st.selectbox("並べ替え", options=["TOTAL"] + DERIVED_KEYS + ABILS, index=0)
            ascending = st.toggle("昇順", value=False, key="hist_asc")

            df_hist = pd.DataFrame(st.session_state.history)
            df_hist = df_hist.sort_values(by=sort_key, ascending=ascending).reset_index(drop=True)
            df_hist["hid_idx"] = df_hist.index

            df_view = df_hist[["hid_idx"] + ABILS + ["TOTAL"] + DERIVED_KEYS].copy()
            df_view.insert(0, "★", False)

            edited = st.data_editor(
                df_view,
                use_container_width=True,
                height=380,
                column_config={"hid_idx": st.column_config.NumberColumn("ID", disabled=True)},
                key="hist_editor"
            )

            idx = st.number_input("採用 ID（上表のID）", min_value=0, max_value=int(df_hist["hid_idx"].max()), value=0, step=1)
            def adopt(hid: int):
                target = st.session_state.history[hid]
                finals = {a: int(target[a]) for a in ABILS}
                basev  = target.get("_base", {a: finals[a] - (target.get("_mods", {}).get(a, 0) if target.get("_apply_mod", True) else 0) for a in ABILS})
                st.session_state.current_stats  = finals
                st.session_state.current_base   = basev
                st.session_state.current_detail = target.get("_detail", {a: [] for a in ABILS})
                st.session_state.current_add    = target.get("_adds", {a: 0 for a in ABILS})

            cH1, cH2 = st.columns(2)
            with cH1:
                if st.button("このIDを現在セットに採用", use_container_width=True):
                    adopt(int(idx))
            with cH2:
                if st.button("チェック行を★に追加", use_container_width=True):
                    added = 0
                    for _, row in edited.iterrows():
                        if bool(row["★"]):
                            hid = int(row["hid_idx"])
                            st.session_state.favorites.insert(0, st.session_state.history[hid])
                            added += 1
                    st.success(f"★に追加：{added} 件")
        else:
            st.info("履歴は空です。サイドバーや上部ボタンでロールしてください。")

    # ---- お気に入り（★）----
    st.subheader("お気に入り（★）")
    if st.session_state.favorites:
        df_fav = pd.DataFrame(st.session_state.favorites)
        st.dataframe(df_fav[ABILS + ["TOTAL"] + DERIVED_KEYS], use_container_width=True, height=260)

        def fav_df_csv():
            rows = []
            for rec in st.session_state.favorites:
                row = {k: rec.get(k, 0) for k in ABILS}
                row.update({k: rec.get(k) for k in ["TOTAL"] + DERIVED_KEYS})
                rows.append(row)
            return pd.DataFrame(rows) if rows else pd.DataFrame()
        csv_bytes = fav_df_csv().to_csv(index=False).encode("utf-8")
        st.download_button("★ をCSVでダウンロード", data=csv_bytes, file_name="coc6_favorites.csv",
                           mime="text/csv", use_container_width=True)

        del_idx = st.number_input("★ 削除 index", min_value=0, max_value=len(st.session_state.favorites)-1, value=0, step=1, key="fav_del_idx")
        cF1, cF2 = st.columns(2)
        with cF1:
            if st.button("この★を削除", use_container_width=True):
                st.session_state.favorites.pop(int(del_idx))
                st.success("削除しました。")
        with cF2:
            if st.button("★ を全削除", use_container_width=True, type="secondary"):
                st.session_state.favorites.clear()
                st.success("★ を空にしました。")
    else:
        st.info("★ は空です。履歴からチェック追加するか、自動お気に入りを使ってね。")


# =========================
# タブ2：プロフィール生成（出身地・性別・誕生日・職業）
# =========================
with tab2:
    st.title("プロフィール生成（出身地・性別・誕生日・職業）")

    colA, colB, colC = st.columns([1,1,2])
    with colA:
        mode = st.radio("国籍モード", ["日本版","世界版"], horizontal=True)
    with colB:
        n_profiles = st.number_input("生成数", min_value=1, max_value=50, value=1, step=1)
    with colC:
        year_min, year_max = st.slider("生年レンジ", min_value=1900, max_value=date.today().year,
                                       value=(1990, 2005), step=1)

    colD, colE = st.columns(2)
    with colD:
        gender_opt = st.selectbox("性別", ["ランダム","男","女","その他"])
    with colE:
        job_mode = st.selectbox("職業セット", ["日本の職業リスト","世界の職業リスト"])

    def gen_profiles(n: int) -> List[Dict[str, Any]]:
        res = []
        for _ in range(n):
            # 性別
            g = random.choice(["男","女","その他"]) if gender_opt == "ランダム" else gender_opt
            # 誕生日
            bd = random_date(int(year_min), int(year_max)).isoformat()
            # 出身地
            if mode == "日本版":
                birthplace = random.choice(PREFECTURES)
            else:
                birthplace = random.choice(WORLD_COUNTRIES)
            # 職業
            if job_mode == "日本の職業リスト":
                job = random.choice(JOBS_JP)
            else:
                job = random.choice(JOBS_WORLD)
            res.append({
                "出身地": birthplace,
                "性別": g,
                "誕生日": bd,
                "職業": job,
            })
        return res

    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        if st.button("🪄 プロフィールを振る", use_container_width=True):
            newrows = gen_profiles(int(n_profiles))
            st.session_state.profile_history[:0] = newrows
            st.success(f"{len(newrows)}件 生成しました。")
    with c2:
        if st.button("🧹 履歴クリア", use_container_width=True):
            st.session_state.profile_history.clear()
            st.info("プロフィール履歴をクリアしました。")
    with c3:
        st.caption("※ 生年レンジ／性別／職業リスト／国籍モードを設定してから振ってね。")

    st.markdown("---")
    st.subheader("プロフィール履歴")

    if st.session_state.profile_history:
        dfp = pd.DataFrame(st.session_state.profile_history)
        st.dataframe(dfp, use_container_width=True, height=360)

        # エクスポート
        csv_bytes = dfp.to_csv(index=False).encode("utf-8")
        st.download_button("CSVでダウンロード", data=csv_bytes, file_name="profiles.csv",
                           mime="text/csv", use_container_width=True)

        json_bytes = json.dumps(st.session_state.profile_history, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button("JSONでダウンロード", data=json_bytes, file_name="profiles.json",
                           mime="application/json", use_container_width=True)
    else:
        st.info("まだプロフィールはありません。『🪄 プロフィールを振る』を押してね。")
