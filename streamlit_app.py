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
    """戻り: (合計値=出目合計+固定加算, 出目配列, 固定加算)"""
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
    st.session_state.current_stats = {a: 0 for a in ABILS}     # 最終値（mod適用後/無効時はベース値）
    st.session_state.current_base  = {a: 0 for a in ABILS}     # ベース値（出目合計+固定加算 or 固定値）
    st.session_state.current_detail= {a: [] for a in ABILS}    # 出目配列
    st.session_state.current_add   = {a: 0 for a in ABILS}     # 固定加算（3d6=0, 2d6+6=6, 3d6+3=3）

    st.session_state.modifiers     = {a: 0 for a in ABILS}
    st.session_state.fixed_values  = {a: None for a in ABILS}

    st.session_state.history       = []   # 最新が先頭
    st.session_state.favorites     = []

    # 自動お気に入り設定
    st.session_state.auto_fav_enabled = True
    st.session_state.auto_fav_mode    = "AND"
    st.session_state.auto_min         = {k: None for k in ALL_KEYS_FOR_RULE}
    st.session_state.auto_max         = {k: None for k in ALL_KEYS_FOR_RULE}

    st.session_state.history_max_keep = 20
    st.session_state.add_roll_to_history = True  # 全体ロールを履歴へ

# ★/履歴のチェック保持＆安定ID
if "uid_counter" not in st.session_state:
    st.session_state.uid_counter = 0
if "hist_selected_uids" not in st.session_state:
    st.session_state.hist_selected_uids = set()
if "fav_selected_uids" not in st.session_state:
    st.session_state.fav_selected_uids = set()

# アクション処理用フラグ
if "_pending_action" not in st.session_state:
    st.session_state._pending_action = None
if "_last_action_msg" not in st.session_state:
    st.session_state._last_action_msg = ""

# =========================
# ヘッダ & グローバル設定
# =========================
st.title("STATUS　　　ALL（全能力を振る）")

apply_mod = st.toggle(
    "モディファイアを最終値に適用する",
    value=True,
    help="OFFで最終値にモディファイアを加算しません（ベース値のみ）。ONで最終値に加算します。"
)

def make_final(abil: str, base_val: int) -> int:
    return base_val + (st.session_state.modifiers[abil] if apply_mod else 0)

# 共通：固定値/ダイス/モディファイアをまとめて適用
def roll_effective(abil: str) -> Tuple[int, List[int], int, int]:
    """
    戻り: base, detail, add, final
      base   … 固定ありなら固定値、なければダイス合計(+固定加算済)
      detail … 出目配列（固定時は []）
      add    … 固定加算（3d6=0, 2d6+6=6, 3d6+3=3）
      final  … base + (モディファイア or 0)
    """
    fixed = st.session_state.fixed_values.get(abil)
    if fixed is not None:
        base = int(fixed); d = []; add = 0
    else:
        base, d, add = roll_for(abil)
    final = base + (st.session_state.modifiers[abil] if apply_mod else 0)
    return base, d, add, final

# ===== スワップ/移動（関数は先に定義しておく） =====
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

# モディファイア/適用トグルが変わったら現在セットを再計算
def _recompute_current_from_mods():
    for abil in ABILS:
        base = st.session_state.current_base.get(abil, 0)
        st.session_state.current_stats[abil] = base + (st.session_state.modifiers[abil] if apply_mod else 0)

if "prev_modifiers" not in st.session_state:
    st.session_state.prev_modifiers = dict(st.session_state.modifiers)
if "prev_apply_mod" not in st.session_state:
    st.session_state.prev_apply_mod = apply_mod

def _check_recompute_mods():
    if (st.session_state.prev_modifiers != st.session_state.modifiers) or (st.session_state.prev_apply_mod != apply_mod):
        _recompute_current_from_mods()
        st.session_state.prev_modifiers = dict(st.session_state.modifiers)
        st.session_state.prev_apply_mod = apply_mod

# ====== ペンディングアクションを最初に処理（“前のボタンが走る”を防ぐ） ======
def _process_pending_action():
    act = st.session_state._pending_action
    if not act:
        return
    msg = ""
    if act["type"] == "swap":
        a, b = act["a"], act["b"]
        if a != b:
            swap(a, b)
            msg = f"{a} と {b} を入れ替えました。"
        else:
            msg = "同じ能力は入れ替えできません。"
    elif act["type"] == "move":
        f, t, x = act["from"], act["to"], int(act["x"])
        if f != t:
            move_points(f, t, x)
            msg = f"{f} -{x} / {t} +{x}（合計不変）"
        else:
            msg = "同じ能力へは移動できません。"
    st.session_state._pending_action = None
    st.session_state._last_action_msg = msg

# 先にモディファイア反映→アクション処理
_check_recompute_mods()
_process_pending_action()

# =========================
# レコード生成・★判定
# =========================
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
    # 安定ID付与（チェック保持用）
    st.session_state.uid_counter += 1
    rec["_uid"] = st.session_state.uid_counter
    return rec

def adopt_record(rec: Dict[str, Any]):
    """履歴/★の1レコードを現在セットに展開して採用"""
    finals = {a: int(rec[a]) for a in ABILS}
    basev  = rec.get("_base", {
        a: finals[a] - (rec.get("_mods", {}).get(a, 0) if rec.get("_apply_mod", True) else 0) for a in ABILS
    })
    st.session_state.current_stats  = finals
    st.session_state.current_base   = basev
    st.session_state.current_detail = rec.get("_detail", {a: [] for a in ABILS})
    st.session_state.current_add    = rec.get("_adds", {a: 0 for a in ABILS})

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
    maxk = int(st.session_state.history_max_keep)
    if len(st.session_state.history) > maxk:
        st.session_state.history = st.session_state.history[:maxk]
    if auto_fav_ok(rec):
        st.session_state.favorites.insert(0, rec)

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
    cond_df = pd.DataFrame({
        "項目": ALL_KEYS_FOR_RULE,
        "下限": [st.session_state.auto_min[k] or 0 for k in ALL_KEYS_FOR_RULE],
        "上限": [st.session_state.auto_max[k] or 0 for k in ALL_KEYS_FOR_RULE],
    })
    edited_cond = st.data_editor(cond_df, use_container_width=True, num_rows="fixed", key="auto_cond_table")
    for _, row in edited_cond.iterrows():
        k = row["項目"]
        lo = int(row["下限"]) if int(row["下限"]) != 0 else None
        hi = int(row["上限"]) if int(row["上限"]) != 0 else None
        st.session_state.auto_min[k] = lo
        st.session_state.auto_max[k] = hi

    # まとめて振る（履歴へ）
    if st.button("まとめて振る（履歴に追加）", use_container_width=True):
        newrecs = []
        for _ in range(int(n_sets)):
            base_vals, finals, detail, adds = {}, {}, {}, {}
            for abil in ABILS:
                base, d, add, final = roll_effective(abil)
                base_vals[abil] = base
                detail[abil]    = d
                adds[abil]      = add
                finals[abil]    = final
            rec = make_record(finals, base_vals, detail, adds)
            newrecs.append(rec)

        # 履歴に前置 → トリム
        st.session_state.history[:0] = newrecs
        maxk = max(5, int(st.session_state.history_max_keep))
        if len(st.session_state.history) > maxk:
            del st.session_state.history[maxk:]

        # 自動★は新規分だけ
        favs = [r for r in newrecs if auto_fav_ok(r)]
        if favs:
            st.session_state.favorites[:0] = favs

        st.success(f"{len(newrecs)} セットを履歴に追加しました（★ {len(favs)} 件）")

    # サイドバーで値が変わった後にもう一度チェック（数値入力に追従）
    _check_recompute_mods()

# =========================
# 全体振り（履歴保存オプションあり）
# =========================
def roll_all_into_current(save_to_history: bool):
    base_vals, finals, detail, adds = {}, {}, {}, {}
    for abil in ABILS:
        base, d, add, final = roll_effective(abil)
        st.session_state.current_base[abil]   = base
        st.session_state.current_detail[abil] = d
        st.session_state.current_add[abil]    = add
        st.session_state.current_stats[abil]  = final

        base_vals[abil] = base
        finals[abil]    = final
        detail[abil]    = d
        adds[abil]      = add

    # レコードは常に作る（★判定のため）
    rec = make_record(finals, base_vals, detail, adds)

    # 履歴保存はトグルに従う
    if save_to_history:
        st.session_state.history.insert(0, rec)
        maxk = max(5, int(st.session_state.history_max_keep))
        if len(st.session_state.history) > maxk:
            del st.session_state.history[maxk:]

    # ★は常に条件判定して自動追加
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

# =========================
# 能力一覧（横並び）＋ TOTAL（EDUの右）
# =========================
st.subheader("能力一覧（横並び）")

def cb_reroll_one(abil: str):
    base, d, add, final = roll_effective(abil)
    st.session_state.current_base[abil]   = base
    st.session_state.current_detail[abil] = d
    st.session_state.current_add[abil]    = add
    st.session_state.current_stats[abil]  = final

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
        final_val = st.session_state.current_stats.get(abil, 0)
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
# 出目入れ替え（イベントフラグ方式で誤発火ゼロ）
# =========================
st.subheader("出目入れ替え（スワップ） / xポイント移動")
if st.session_state._last_action_msg:
    st.info(st.session_state._last_action_msg)

colL, colR = st.columns(2)

# 左：入れ替え（ボタンはフラグセットのみ）
with colL:
    st.selectbox("入れ替え元", ABILS, index=0, key="swap_a")
    st.selectbox("入れ替え先", ABILS, index=1, key="swap_b")
    if st.button("↔ 入れ替える", use_container_width=True, key="swap_btn"):
        st.session_state._pending_action = {"type": "swap", "a": st.session_state.swap_a, "b": st.session_state.swap_b}

# 右：ポイント移動（ボタンはフラグセットのみ）
with colR:
    st.selectbox("減らす能力", ABILS, index=0, key="move_from")
    st.selectbox("増やす能力", ABILS, index=1, key="move_to")
    st.number_input("移動ポイント", min_value=1, max_value=50, value=1, step=1, key="move_x")
    if st.button("➕➖ 移動を実行", use_container_width=True, key="move_btn"):
        st.session_state._pending_action = {
            "type": "move", "from": st.session_state.move_from, "to": st.session_state.move_to, "x": st.session_state.move_x
        }

# 範囲警告（ベース値で評価）
warns = []
for k in ABILS:
    v = st.session_state.current_base.get(k, 0)
    if v < WARN_MIN[k] or v > WARN_MAX[k]:
        warns.append(f"{k} が範囲外（{v} / 推奨 {WARN_MIN[k]}〜{WARN_MAX[k]}）")
if warns:
    st.warning(" / ".join(warns))

st.markdown("---")

# =========================
# 派生ステータス
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
# 履歴（並べ替え・採用・★チェック保持）
# =========================
with st.expander("履歴（並べ替え・採用・★チェック）", expanded=False):
    if st.session_state.history:
        sort_key = st.selectbox("並べ替え", options=["TOTAL"] + DERIVED_KEYS + ABILS, index=0)
        ascending = st.toggle("昇順", value=False, key="hist_asc")

        df_hist = pd.DataFrame(st.session_state.history)
        if "_uid" not in df_hist.columns:
            df_hist["_uid"] = range(10_000, 10_000 + len(df_hist))
        df_hist = df_hist.sort_values(by=sort_key, ascending=ascending).reset_index(drop=True)

        cols_show = ["_uid"] + ABILS + ["TOTAL"] + DERIVED_KEYS
        df_view = df_hist[cols_show].copy()
        df_view.insert(0, "★チェック", df_view["_uid"].isin(st.session_state.hist_selected_uids))

        edited = st.data_editor(
            df_view,
            use_container_width=True,
            height=380,
            column_config={"_uid": st.column_config.NumberColumn("UID", disabled=True)},
            key="hist_editor"
        )
        st.session_state.hist_selected_uids = set(edited.loc[edited["★チェック"] == True, "_uid"].tolist())

        idx = st.number_input("採用（履歴の先頭=0）", min_value=0, max_value=max(0, len(st.session_state.history)-1), value=0, step=1)
        cH1, cH2, cH3 = st.columns(3)
        with cH1:
            if st.button("このIDを現在セットに採用", use_container_width=True):
                adopt_record(st.session_state.history[int(idx)])
        with cH2:
            if st.button("チェック行を★に追加", use_container_width=True):
                added = 0
                uids = st.session_state.hist_selected_uids
                for rec in st.session_state.history:
                    if rec.get("_uid") in uids:
                        st.session_state.favorites.insert(0, rec)
                        added += 1
                st.success(f"★に追加：{added} 件")
        with cH3:
            if st.button("チェック先頭を現在セットに採用", use_container_width=True):
                picked = next((r for r in st.session_state.history if r.get("_uid") in st.session_state.hist_selected_uids), None)
                if picked:
                    adopt_record(picked)
                    st.success("チェック先頭の1件を採用しました。")
                else:
                    st.info("チェックがありません。")
    else:
        st.info("履歴は空です。サイドバーや上部ボタンでロールしてください。")

# =========================
# お気に入り（★） — 履歴風UI（チェック保持・採用・削除）
# =========================
st.subheader("お気に入り（★）")
if st.session_state.favorites:
    df_fav = pd.DataFrame(st.session_state.favorites)
    if "_uid" not in df_fav.columns:
        df_fav["_uid"] = range(20_000, 20_000 + len(df_fav))

    sort_key_f = st.selectbox("並べ替え（★）", options=["TOTAL"] + DERIVED_KEYS + ABILS, index=0, key="fav_sort_key")
    ascending_f = st.toggle("昇順（★）", value=False, key="fav_asc")

    if sort_key_f in df_fav.columns:
        df_fav = df_fav.sort_values(by=sort_key_f, ascending=ascending_f).reset_index(drop=True)

    cols_show_f = ["_uid"] + ABILS + ["TOTAL"] + DERIVED_KEYS
    df_view_f = df_fav[cols_show_f].copy()
    df_view_f.insert(0, "✓", df_view_f["_uid"].isin(st.session_state.fav_selected_uids))

    edited_f = st.data_editor(
        df_view_f,
        use_container_width=True,
        height=360,
        column_config={"_uid": st.column_config.NumberColumn("UID", disabled=True)},
        key="fav_editor"
    )
    st.session_state.fav_selected_uids = set(edited_f.loc[edited_f["✓"] == True, "_uid"].tolist())

    cF1, cF2, cF3 = st.columns(3)
    with cF1:
        if st.button("選択行を現在セットに採用", use_container_width=True):
            picked = next((rec for rec in st.session_state.favorites if rec.get("_uid") in st.session_state.fav_selected_uids), None)
            if picked:
                adopt_record(picked)
                st.success("★から採用しました。")
            else:
                st.info("チェックがありません。")

    with cF2:
        if st.button("選択行を★から削除", use_container_width=True):
            if st.session_state.fav_selected_uids:
                st.session_state.favorites = [
                    rec for rec in st.session_state.favorites
                    if rec.get("_uid") not in st.session_state.fav_selected_uids
                ]
                st.session_state.fav_selected_uids.clear()
                st.success("選択した★を削除しました。")
            else:
                st.info("チェックがありません。")

    with cF3:
        # CSVエクスポート
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

    if st.button("★ を全削除", use_container_width=True, type="secondary"):
        st.session_state.favorites.clear()
        st.session_state.fav_selected_uids.clear()
        st.success("★ を空にしました。")
else:
    st.info("★ は空です。履歴からチェック追加するか、自動お気に入りを使ってね。")
