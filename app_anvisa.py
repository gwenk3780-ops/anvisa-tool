# app_anvisa.py
# 本地 ANVISA 成分补剂授权查询工具（批量查询 + 纵向详情）
# 功能：规范化 + 别名映射 + CAS 支持 + 中文表头 + 批量查询 + Tabs + 导出 Excel

import re
import io
import os
import pandas as pd
from unidecode import unidecode
import streamlit as st

# ===================== 1. 配置区域 =====================

DB_PATH = "anvisa_final_v10.xlsx"
ALIAS_PATH = "anvisa_alias_total.xlsx"

st.set_page_config(
    page_title="Anvisa 合规查询工具（本地版）",
    layout="wide",
    page_icon="🇧🇷",
)

# ===================== 2. 文本规范化函数 =====================

def normalize(text: str) -> str:
    """统一规范化成分名字 / 别名，用于匹配（去重音 + 小写 + 去多余空格）。"""
    if text is None:
        return ""

    text = str(text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip().strip('"').strip("'")
    text = text.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
    for ch in ["–", "—", "−"]:
        text = text.replace(ch, "-")
    text = unidecode(text)
    text = text.lower()
    return text


# ===================== 3. 数据加载 =====================

@st.cache_data
def load_db(db_path: str) -> pd.DataFrame | None:
    if not os.path.exists(db_path):
        return None
    df = pd.read_excel(db_path)

    if "Ingredient (成分)" not in df.columns:
        st.error("在主数据库里找不到列：'Ingredient (成分)'，请检查列名或 Excel 文件。")
        st.stop()

    df["__norm_ingredient"] = df["Ingredient (成分)"].apply(normalize)

    if "CAS" in df.columns:
        df["CAS"] = df["CAS"].astype(str)
        df["__norm_cas"] = df["CAS"].apply(normalize)

    return df


@st.cache_data
def load_alias(alias_path: str) -> pd.DataFrame:
    if not os.path.exists(alias_path):
        return pd.DataFrame(columns=["Alias", "Official", "__norm_alias", "__norm_official"])

    alias_df = pd.read_excel(alias_path)
    required_cols = {"Alias", "Official"}
    if not required_cols.issubset(alias_df.columns):
        return pd.DataFrame(columns=["Alias", "Official", "__norm_alias", "__norm_official"])

    alias_df["Alias"] = alias_df["Alias"].astype(str)
    alias_df["Official"] = alias_df["Official"].astype(str)
    alias_df["__norm_alias"] = alias_df["Alias"].apply(normalize)
    alias_df["__norm_official"] = alias_df["Official"].apply(normalize)
    return alias_df


# ===================== 4. 查询逻辑 =====================

def search_ingredients(df: pd.DataFrame, alias_df: pd.DataFrame, query: str) -> pd.DataFrame:
    norm_q = normalize(query)
    if not norm_q:
        return df.iloc[0:0].copy()

    mask_ing = df["__norm_ingredient"].str.contains(norm_q, na=False)

    if "__norm_cas" in df.columns:
        mask_cas = df["__norm_cas"].str.contains(norm_q, na=False)
    else:
        mask_cas = False

    if not alias_df.empty:
        alias_hits = alias_df[alias_df["__norm_alias"].str.contains(norm_q, na=False)]
        target_official_norms = alias_hits["__norm_official"].unique()
        if len(target_official_norms) > 0:
            mask_alias = df["__norm_ingredient"].isin(target_official_norms)
        else:
            mask_alias = False
    else:
        mask_alias = False

    final_mask = mask_ing | mask_cas | mask_alias
    result = df[final_mask].copy()
    return result


# ===================== 5. 全局表格样式（给纵向 st.table 用） =====================

st.markdown(
    """
    <style>
    /* 让 st.table 撑满容器宽度，长内容在单元格内自动换行 */
    div[data-testid="stTable"] table {
        width: 100%;
        table-layout: auto;
        border-collapse: collapse;
    }

    /* 通用单元格样式：左对齐 + 自动换行 */
    div[data-testid="stTable"] thead tr th,
    div[data-testid="stTable"] tbody tr td {
        text-align: left !important;
        vertical-align: middle !important;
        white-space: normal !important;
        word-break: break-word !important;
        overflow-wrap: break-word !important;
        padding: 0.5rem 0.75rem;
    }

    /* 把第二列（“字段”这一列）设宽一点，并且不拆行 */
    div[data-testid="stTable"] thead tr th:nth-child(2),
    div[data-testid="stTable"] tbody tr td:nth-child(2) {
        width: 140px;
        min-width: 140px;
        white-space: nowrap !important;
    }

    /* 控制表格里所有文字字号 */
    div[data-testid="stTable"] * {
        font-size: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ===================== 6. 页面 UI 布局 =====================

st.title("🇧🇷 巴西 Anvisa 保健品成分合规查询")
st.markdown("---")

df = load_db(DB_PATH)
alias_df = load_alias(ALIAS_PATH)

with st.sidebar:
    st.header("📊 数据库状态")
    if df is not None:
        st.success(f"✅ 已加载数据库: {DB_PATH}")

        if "Ingredient (成分)" in df.columns:
            st.markdown("**主要成分列:** Ingredient (成分)")

    else:
        st.error("❌ 未找到主数据库文件！请确保 anvisa_final_v10.xlsx 在同目录下。")

    st.markdown("---")
    st.header("💡 使用说明")
    st.markdown(
        """
        1. 在右侧输入框**一行一个**成分名称。  
        2. 支持：葡语、英文、拉丁文、中文、CAS 号。  
        3. **模糊搜索 + 去重音**：输入 `Cafeina` 也能匹配 `Cafeína`。  
        4. 查询结果支持导出为 Excel。
        """
    )

if df is None:
    st.warning("请先把 anvisa_final_v10.xlsx 放到当前目录，然后重新运行此工具。")
    st.stop()

st.subheader("🔍 成分批量查询")
input_text = st.text_area(
    "请输入成分名称（每行一个，例如：Cafeina、Vitamina C、Melatonina 或中文名 / CAS）：",
    height=150,
)

# ===================== 7. 批量查询 + 纵向展示 =====================

final_found_df = pd.DataFrame()
results_not_found = []

if st.button("🚀 开始查询", type="primary"):
    if not input_text.strip():
        st.warning("请输入至少一个成分！")
    else:
        user_queries = [line.strip() for line in input_text.split("\n") if line.strip()]

        results_found = []
        results_not_found = []

        progress_bar = st.progress(0.0)

        for idx, query in enumerate(user_queries):
            progress_bar.progress((idx + 1) / len(user_queries))

            matches = search_ingredients(df, alias_df, query)

            if not matches.empty:
                rename_map = {
                    "Ingredient (成分)": "成分",
                    "CAS": "CAS",
                    "Specs (规格)": "规格",
                    "Function (功能)": "功能",
                    "Claims (声称)": "声称",
                    "Labeling (标签)": "标签",
                    "Other (其他)": "其他",
                    "Link (链接)": "链接",
                }

                exist_cols = [c for c in rename_map.keys() if c in matches.columns]
                display_df = matches[exist_cols].copy()
                display_df.rename(columns=rename_map, inplace=True)

                display_df.insert(0, "查询词", query)
                display_df.insert(1, "是否授权", "✅ YES")

                results_found.append(display_df)
            else:
                results_not_found.append(
                    {
                        "查询词": query,
                        "是否授权": "❌ NO（未在库中找到）",
                        "建议": "请检查拼写，或在别名表 anvisa_alias_total.xlsx 中补充该写法",
                    }
                )

        progress_bar.empty()
        st.markdown("---")

        tab1, tab2 = st.tabs(["✅ 已授权 / 找到的成分（纵向详情）", "❌ 未找到的成分"])

        with tab1:
            if results_found:
                final_found_df = pd.concat(results_found, ignore_index=True)
                st.success(f"共匹配到 {len(final_found_df)} 条相关记录")

                # 🔽 对每条记录，转成“字段 / 内容”的纵向表格
                for i, row in final_found_df.iterrows():
                    st.markdown(
                        f"**🔹 查询词：`{row['查询词']}` —— 匹配成分：`{row['成分']}`**"
                    )

                    vertical_df = row.to_frame().reset_index()
                    vertical_df.columns = ["字段", "内容"]
                    vertical_df = vertical_df.reset_index(drop=True)

                    st.table(vertical_df)
                    st.markdown("---")
            else:
                st.write("没有找到匹配的已授权成分。")

        with tab2:
            if results_not_found:
                not_found_df = pd.DataFrame(results_not_found)
                st.error(f"有 {len(not_found_df)} 个查询词未找到匹配项")
                st.dataframe(not_found_df, use_container_width=True)
            else:
                st.write("所有查询词都找到了匹配项！")

        # ===================== 8. 导出 Excel 报告 =====================

        st.markdown("---")
        st.subheader("📥 导出查询结果")

        if final_found_df.empty and not results_not_found:
            st.info("当前没有可导出的数据，请先执行一次查询。")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                if not final_found_df.empty:
                    final_found_df.to_excel(writer, sheet_name="已授权成分", index=False)
                if results_not_found:
                    pd.DataFrame(results_not_found).to_excel(
                        writer, sheet_name="未找到成分", index=False
                    )
            output.seek(0)

            st.download_button(
                label="下载查询结果（Excel）",
                data=output,
                file_name="Anvisa_查询结果报告.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
