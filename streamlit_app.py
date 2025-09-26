# streamlit_app.py
import math
import random
from typing import Dict, List, Tuple, Any

import pandas as pd
import streamlit as st

st.set_page_config(page_title="CoC6 能力値振りツール", layout="wide", initial_sidebar_state="expanded")

# =========================
# 定数・ユーティリティ
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
# セッション初期化
# =========================
if "current_stats" not in st.session_state:
    st.session_state.current_stats = {a: 0 for a in ABILS}     # 最終値（mod適用後/無効時は素のまま）
    st.session_state.current_base  = {a: 0 for a in ABILS}     # 素の合計（出目合計+固定加算）
    st.session_state.current_detail= {a: [] for a in ABILS}    # 出目配列
    st.session_state.current_add   = {a: 0 for a in ABILS}     # 固定加算

    st.session_state.modifiers     = {a: 0 for a in ABILS}
    st.session_state.fixed_values  = {a: None for a in ABILS}

    st.session_state.history       = []   # 最新が先頭
    st.session_state.favorites     = []

    # 履歴レコードの安定ID
    st.session_state._hid_counter  = 0

    # 自動お気に入り設定（min/max をまとめて持つ）
    st.session_state.auto_fav_enabled = True
    st.session_state.auto_fav_mode    = "AND"
    st.session_state.auto_min         = {k: None for k in ALL_KEYS_FOR_RULE}
    st.session_state.auto_max         = {k: None for k in ALL_KEYS_FOR_RULE}

    st.session_state.history_max_keep = 20
    st.session_state.add_roll_to_history = True  # 全能力ロールを履歴へ

# =========================
# ヘッダ & グローバル設定
# =========================
st.title("STATUS　　　ALL（全能力を振る）")

apply_mod = st.toggle(
    "モディファイアを最終値に適用する",
    value=True,
    help="OFFで最終値にモディファイアを加算しません（素の合計のみ）。ONで最終値に加算します。"
)

def make_final(abil: str, base_val: int) -> int:
    return base_val + (st.session_state.modifiers[abil] if apply_mod else 0)

# =========================
# 自動お気に入り判定 & 履歴追記
# =========================
def make_record(finals: Dict[str, int],
                base_vals: Dict[str, int],
                detail: Dict[str, List[int]],
                adds: Dict[str, int]) -> Dict[str, Any]:
    rec = {
        "hid": st.session_state._hid_counter,  # 安定ID
        **finals,
        "TOTAL": total_score(finals),
        **derived_stats(finals),
        "_base": base_vals, "_detail": detail, "_adds": adds,
        "_mods": dict(st.session_state.modifiers),
        "_apply_mod": apply_mod,
    }
    st.session_state._hid_counter += 1
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

def history_append(rec: Dict[str, Any]):
    st.session_state.history.insert(0, rec)
    # 最大件数で切り詰め
    maxk = int(st.session_state.history_max_keep)
    if len(st.session_state.history) > maxk:
        st.session_state.history = st.session_state.history[:maxk]
    # 自動お気に入り
    if auto_fav_ok(rec):
        st.session_state.favorites.insert(0, rec)

def find_history_by_hid(hid: int) -> Dict[str, Any]:
    for r in st.session_state.history:
        if r.get("hid") == hid:
            return r
    # 見つからなければ先頭（フォールバック）
    return st.session_state.history[0] if st.session_state.history else {}

# =========================
# サイドバー：まとめて振る（履歴へ）
# =========================
with st.sidebar:
    st.title("操作パネル")

    st.subheader("まとめて振る（履歴に追加）")
    n_sets = st.number_input("セット数（最大5）", min_value=1, max_value=5, value=1, step=1)

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

    st.markdown("---")
    st.subheader("履歴・★ 設定")
    st.session_state.history_max_keep = st.number_input("履歴の最大保持数", min_value=5, max_value=200, value=20, step=1)
    st.checkbox("全体ロールを履歴に保存する", value=st.session_state.add_roll_to_history, key="add_roll_to_history")

    st.checkbox("自動お気に入りを有効化", value=st.session_state.auto_fav_enabled, key="auto_fav_enabled")
    st.radio("条件の結合", options=["AND", "OR"],
             index=0 if st.session_state.auto_fav_mode=="AND" else 1,
             key="auto_fav_mode", horizontal=True)

    st.caption("自動お気に入りの範囲条件（下限/上限）。空=0で未指定。対象：全能力・全派生・TOTAL")
    # 表でまとめて編集（見やすく）
    cond_df = pd.DataFrame({
        "項目": ALL_KEYS_FOR_RULE,
        "下限": [st.session_state.auto_min[k] or 0 for k in ALL_KEYS_FOR_RULE],
        "上限": [st.session_state.auto_max[k] or 0 for k in ALL_KEYS_FOR_RULE],
    })
    edited_cond = st.data_editor(cond_df, use_container_width=True, num_rows="fixed", key="auto_cond_table")
    # セッションへ反映
    for _, row in edited_cond.iterrows():
        k = row["項目"]
        lo = int(row["下限"]) if int(row["下限"]) != 0 else None
        hi = int(row["上限"]) if int(row["上限"]) != 0 else None
        st.session_state.auto_min[k] = lo
        st.session_state.auto_max[k] = hi

    # その場処理で確実に動作
    if st.button("まとめて振る（履歴に追加）", use_container_width=True):
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
            history_append(rec)
        st.success(f"{int(n_sets)} セットを履歴に追加しました。")

# =========================
# 全能力を振る（履歴保存オプションあり）
# =========================
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
        history_append(rec)

b1, b3 = st.columns([1,2])
with b1:
    if st.button("🎲 全能力を振る", use_container_width=True):
        roll_all_into_current(st.session_state.add_roll_to_history)
        st.success("現在セットを新規ロールしました。")
with b3:
    st.caption("固定あり→固定値／固定なし→ダイス。履歴保存はトグルでON/OFF。最終値はモディファイア設定に従う。")

st.markdown("---")

# =========================
# 能力一覧（横並び）＋ TOTAL（EDUの右）
# =========================
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

# 8能力＋TOTALで9列
cols = st.columns(len(ABILS) + 1)

# 各能力
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

# TOTAL（EDUの右）
with cols[-1]:
    finals_now = {a: st.session_state.current_stats[a] for a in ABILS}
    st.markdown("### TOTAL  \n<small>sum of abilities</small>", unsafe_allow_html=True)
    st.metric("合計", total_score(finals_now))

st.markdown("---")

# =========================
# 派生ステータス（← ここをスワップより先に表示）
# =========================
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

# =========================
# 出目入れ替え（スワップ） / xポイント移動（← 派生の後に移動）
# =========================
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

# =========================
# 履歴（並べ替え・採用・★チェック）
# =========================
with st.expander("履歴（並べ替え・採用・★チェック）", expanded=False):
    if st.session_state.history:
        sort_key = st.selectbox("並べ替え", options=["TOTAL"] + DERIVED_KEYS + ABILS, index=0)
        ascending = st.toggle("昇順", value=False, key="hist_asc")

        df_hist = pd.DataFrame(st.session_state.history)
        df_hist = df_hist.sort_values(by=sort_key, ascending=ascending, ignore_index=True)
        # 安定ID（hid）で原本を参照
        df_view = df_hist[["hid"] + ABILS + ["TOTAL"] + DERIVED_KEYS].copy()
        df_view.insert(0, "★", False)  # チェック列

        edited = st.data_editor(
            df_view,
            use_container_width=True,
            height=380,
            column_config={"hid": st.column_config.NumberColumn("ID", disabled=True)},
            key="hist_editor"
        )

        # 採用
        sel_hid = st.number_input("採用 ID（上表のID）", min_value=0, value=int(df_view["hid"].min()), step=1)
        def adopt(hid: int):
            target = find_history_by_hid(hid)
            if not target: return
            finals = {a: int(target[a]) for a in ABILS}
            basev  = target.get("_base", {a: finals[a] - (target.get("_mods", {}).get(a, 0) if target.get("_apply_mod", True) else 0) for a in ABILS})
            st.session_state.current_stats  = finals
            st.session_state.current_base   = basev
            st.session_state.current_detail = target.get("_detail", {a: [] for a in ABILS})
            st.session_state.current_add    = target.get("_adds", {a: 0 for a in ABILS})

        cH1, cH2 = st.columns(2)
        with cH1:
            if st.button("このIDを現在セットに採用", use_container_width=True):
                adopt(int(sel_hid))
        with cH2:
            if st.button("チェック行を★に追加", use_container_width=True):
                added = 0
                for _, row in edited.iterrows():
                    if bool(row["★"]):
                        hid = int(row["hid"])
                        rec = find_history_by_hid(hid)
                        if rec:
                            st.session_state.favorites.insert(0, rec)
                            added += 1
                st.success(f"★に追加：{added} 件")
    else:
        st.info("履歴は空です。サイドバーや上部ボタンでロールしてください。")

# =========================
# お気に入り（★）— インポート/エクスポート対応
# =========================
st.subheader("お気に入り（★）")

# --- インポート ---
with st.expander("★ インポート（CSV/JSON）", expanded=False):
    up = st.file_uploader("CSV もしくは JSON を選択", type=["csv", "json"])
    if up is not None:
        try:
            if up.name.lower().endswith(".json"):
                data = pd.read_json(up).to_dict(orient="records") if up.type == "application/json" else \
                       pd.read_json(up).to_dict(orient="records")
                # JSONは「レコード配列」を想定
                for rec in data:
                    # 必須: ABILS を埋める
                    finals = {a: int(rec.get(a, 0)) for a in ABILS}
                    out = {
                        **finals,
                        "TOTAL": rec.get("TOTAL", total_score(finals)),
                        **derived_stats(finals),
                        "_base": rec.get("_base", finals.copy()),
                        "_detail": rec.get("_detail", {a: [] for a in ABILS}),
                        "_adds": rec.get("_adds", {a: 0 for a in ABILS}),
                        "_mods": rec.get("_mods", {a: 0 for a in ABILS}),
                        "_apply_mod": bool(rec.get("_apply_mod", True)),
                    }
                    # hid は重複防止のため付けない（お気に入りでは不要）
                    st.session_state.favorites.insert(0, out)
                st.success(f"JSON から {len(data)} 件インポートしました。")
            else:
                df = pd.read_csv(up)
                cnt = 0
                for _, row in df.iterrows():
                    finals = {a: int(row.get(a, 0)) for a in ABILS}
                    out = {
                        **finals,
                        "TOTAL": int(row.get("TOTAL", total_score(finals))),
                        **derived_stats(finals),
                        "_base": finals.copy(),
                        "_detail": {a: [] for a in ABILS},
                        "_adds": {a: 0 for a in ABILS},
                        "_mods": {a: 0 for a in ABILS},
                        "_apply_mod": True,
                    }
                    st.session_state.favorites.insert(0, out); cnt += 1
                st.success(f"CSV から {cnt} 件インポートしました。")
        except Exception as e:
            st.error(f"インポート失敗: {e}")

# --- 一覧 & エクスポート ---
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

    # エクスポート（CSV/JSON）
    csv_bytes = fav_df_csv().to_csv(index=False).encode("utf-8")
    st.download_button("★ をCSVでダウンロード", data=csv_bytes, file_name="coc6_favorites.csv",
                       mime="text/csv", use_container_width=True)

    import json
    json_bytes = json.dumps(st.session_state.favorites, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button("★ をJSONでダウンロード", data=json_bytes, file_name="coc6_favorites.json",
                       mime="application/json", use_container_width=True)

    # 削除系
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
