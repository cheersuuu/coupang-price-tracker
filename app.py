import re
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="쿠팡 가격 트래커", page_icon="📦", layout="wide")


def classify_group(name):
    name = str(name)
    if "울트라" in name:
        return "울트라"
    if "디럭스" in name:
        return "디럭스"
    # AA/AAA 단어 단위 매칭 (AAAA 제외), "오리지널" 키워드도 포함
    if re.search(r'\bAAA\b|\bAA\b', name) and ("알카라인" in name or "오리지널" in name):
        return "오리지널"
    if any(x in name for x in ["2032", "2025", "2016"]):
        return "리튬코인"
    if any(x in name for x in ["C형", "D형", "9V"]):
        return "C/D/9V"
    return "기타특수"


def classify_braun_group(name):
    name = str(name)
    if re.search(r'IPL|바디\s*트리머', name):
        return "IPL/바디트리머"
    if re.search(r'LEVANT|레반트', name, re.IGNORECASE):
        return "LEVANT"
    if re.search(r'울트라\s*씬', name):
        return "울트라씬"
    m = re.search(r"시리즈\s*(\d+)", name)
    if m:
        return "시리즈" + m.group(1)
    return "기타"


@st.cache_data(ttl=300)
def load_data():
    df = pd.read_csv("data.csv", parse_dates=["Date"])
    df["SKU"] = df["상품명"] + " " + df["개수"].fillna("")
    df["SKU"] = df["SKU"].str.strip()
    if "브랜드" not in df.columns:
        df["브랜드"] = "duracell"
    # braun: 상품명 앞 (인기) 제거 + 브라운 → BRAUN 통일
    braun_mask = df["브랜드"] == "braun"
    df.loc[braun_mask, "상품명"] = (
        df.loc[braun_mask, "상품명"]
        .str.replace(r"^\s*\(인기\)\s*", "", regex=True)
        .str.replace(r"^브라운\s*", "BRAUN ", regex=True)
    )
    # braun: 상품명에 제모 포함 시 IPL 통일명 + 모델명
    def normalize_ipl_model(model):
        model = str(model)
        if "PL5257" in model:
            return "PL5257"
        if "6031" in model:
            return "PL5154"
        return model

    ipl_mask = (df["브랜드"] == "braun") & df["상품명"].str.contains("제모", na=False)
    df.loc[ipl_mask, "상품명"] = "BRAUN 실크 엑스퍼트 프로 파이브 IPL " + df.loc[ipl_mask, "개수"].apply(normalize_ipl_model)
    # braun: 모델명이 cc로 끝나고 시리즈명이 +로 안 끝나면 +세척충전스테이션 추가
    braun_cc_mask = (
        (df["브랜드"] == "braun") &
        df["개수"].str.endswith("cc", na=False) &
        ~df["상품명"].str.endswith("+", na=False) &
        ~df["상품명"].str.contains("파워.?케이스", na=False, regex=True) &
        ~df["상품명"].str.contains("세척", na=False)
    )
    df.loc[braun_cc_mask, "상품명"] = df.loc[braun_cc_mask, "상품명"] + "+ 세척 충전 스테이션 세트"
    df["그룹"] = df.apply(
        lambda r: (
            "LEVANT" if r["브랜드"] == "braun" and str(r.get("개수", "")).startswith(("73-", "53-"))
            else classify_braun_group(r["상품명"]) if r["브랜드"] == "braun"
            else classify_group(r["상품명"])
        ),
        axis=1,
    )
    # 품절 문자열은 NaN으로 처리해 숫자 연산 가능하게
    df["가격"] = pd.to_numeric(df["가격"], errors="coerce")
    # merge 키: itemID 있으면 그대로, 없으면 productID+vendorItemID 조합
    df["_mk"] = df.apply(
        lambda r: str(r["itemID"]) if str(r["itemID"]).strip() not in ("", "nan")
                  else f"{r['productID']}_{r['vendorItemID']}",
        axis=1
    )
    return df


def fmt_price(val):
    try:
        return f"{int(float(val)):,}원"
    except:
        return "품절"


VALID_BRANDS = ["braun", "duracell"]

df = load_data()
brands = [b for b in sorted(df["브랜드"].unique()) if b in VALID_BRANDS]

st.title("📦 쿠팡 가격 트래킹 대시보드")

tabs = st.tabs([b.upper() for b in brands])

for tab, brand in zip(tabs, brands):
    with tab:
        bdf = df[df["브랜드"] == brand].copy()
        dates = sorted(bdf["Date"].dt.date.unique())
        latest = max(dates)
        prev = dates[-2] if len(dates) >= 2 else None

        st.caption(f"마지막 업데이트: {latest}")

        BRAUN_KEY_MODELS = ["9665cc", "9615s", "9597cc", "9450cc", "9457cc"]

        # ── 주요상품 섹션 (브라운 전용)
        if brand == "braun":
            st.subheader("⭐ 주요상품")
            key_latest = bdf[bdf["Date"].dt.date == latest].copy()
            key_latest = key_latest[key_latest["개수"].isin(BRAUN_KEY_MODELS)]

            if prev:
                prev_df_key = bdf[bdf["Date"].dt.date == prev].copy()
                key_merged = key_latest.merge(prev_df_key[["_mk", "가격"]], on="_mk", suffixes=("", "_prev"))
                key_merged["변동"] = key_merged["가격"] - key_merged["가격_prev"]

                def color_delta_key(val):
                    if val > 0: return "color: red"
                    elif val < 0: return "color: blue"
                    return "color: gray"

                key_show = key_merged[["상품명", "개수", "수량", "가격_prev", "가격", "변동"]].copy()
                key_show.columns = ["시리즈", "모델명/품번", "색상", "전일가", "현재가", "변동"]
                key_show = key_show.sort_values("모델명/품번")
                key_show["전일가"] = key_show["전일가"].apply(fmt_price)
                key_show["현재가"] = key_show["현재가"].apply(fmt_price)
                key_show["변동"]   = key_show["변동"].apply(lambda v: f"{int(v):+,}원" if pd.notna(v) else "품절")
                st.dataframe(
                    key_show.style.map(color_delta_key, subset=["변동"]),
                    use_container_width=True, hide_index=True,
                )
            else:
                key_show = key_latest[["상품명", "개수", "수량", "가격"]].copy()
                key_show.columns = ["시리즈", "모델명/품번", "색상", "현재가"]
                key_show = key_show.sort_values("모델명/품번")
                key_show["현재가"] = key_show["현재가"].apply(fmt_price)
                st.dataframe(
                    key_show,
                    use_container_width=True, hide_index=True,
                )

            st.divider()

        # ── 그룹 필터
        if brand == "braun":
            braun_groups = ["전체", "울트라씬", "시리즈9", "LEVANT", "시리즈7", "시리즈5", "IPL/바디트리머", "기타"]
            selected_group = st.radio("시리즈", braun_groups, horizontal=True,
                                      key=f"group_{brand}", label_visibility="collapsed")
        else:
            duracell_groups = ["전체", "오리지널", "디럭스", "울트라", "C/D/9V", "리튬코인", "기타특수"]
            selected_group = st.radio("그룹", duracell_groups, horizontal=True,
                                      key=f"group_{brand}", label_visibility="collapsed")

        def filter_group(dataframe):
            if selected_group == "전체":
                return dataframe
            return dataframe[dataframe["그룹"] == selected_group]

        st.divider()

        # ── 요약 지표
        latest_df = filter_group(bdf[bdf["Date"].dt.date == latest].copy())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("추적 상품 수", f"{len(latest_df)}개")

        if prev:
            prev_df = bdf[bdf["Date"].dt.date == prev].copy()
            merged = latest_df.merge(prev_df[["_mk", "가격"]], on="_mk", suffixes=("", "_prev"))
            merged["변동"] = merged["가격"] - merged["가격_prev"]
            up = (merged["변동"] > 0).sum()
            down = (merged["변동"] < 0).sum()
            c2.metric("가격 인상", f"{up}개", delta=f"+{up}", delta_color="inverse")
            c3.metric("가격 인하", f"{down}개", delta=f"-{down}", delta_color="normal")
            c4.metric("변동 없음", f"{len(merged)-up-down}개")
        else:
            c2.metric("가격 인상", "-")
            c3.metric("가격 인하", "-")
            c4.metric("변동 없음", "-")

        st.divider()

        # ── 전일 대비 변동 표
        st.subheader("📊 전일 대비 가격 변동")
        if prev and len(merged) > 0:
            if brand == "braun":
                delta_df = merged[["상품명", "개수", "수량", "가격_prev", "가격", "변동"]].copy()
                delta_df.columns = ["시리즈", "모델명/품번", "색상", "전일가", "현재가", "변동"]
            else:
                delta_df = merged[["SKU", "개수", "수량", "가격_prev", "가격", "변동"]].copy()
                delta_df.columns = ["SKU", "개수", "수량", "전일가", "현재가", "변동"]
            delta_df = delta_df.sort_values("변동")
            delta_df["전일가"] = delta_df["전일가"].apply(fmt_price)
            delta_df["현재가"] = delta_df["현재가"].apply(fmt_price)
            delta_df["변동"]   = delta_df["변동"].apply(lambda v: f"{int(v):+,}원" if pd.notna(v) else "품절")

            def color_delta(val):
                if isinstance(val, str) and "+" in val: return "color: red"
                elif isinstance(val, str) and val.startswith("-"): return "color: blue"
                return "color: gray"

            st.dataframe(
                delta_df.style.map(color_delta, subset=["변동"]),
                use_container_width=True, height=400,
            )
        else:
            st.info("비교할 이전 날짜 데이터가 없습니다.")

        st.divider()

        # ── 가격 추이
        st.subheader("📈 상품별 가격 추이")
        filtered_df = filter_group(bdf)
        sku_options = sorted(filtered_df["SKU"].dropna().unique())
        chart_label = "모델" if brand == "braun" else "SKU"
        selected = st.multiselect("상품 선택", sku_options, default=sku_options[:5], key=f"skus_{brand}")

        if selected:
            chart_df = filtered_df[filtered_df["SKU"].isin(selected)]
            fig = px.line(chart_df, x="Date", y="가격", color="SKU",
                          markers=True,
                          labels={"가격": "가격 (원)", "Date": "날짜", "SKU": chart_label})
            fig.update_layout(height=450, legend=dict(orientation="h", yanchor="bottom", y=1.02))
            fig.update_yaxes(tickformat=",")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── 전체 목록
        st.subheader("📋 현재 가격 전체 목록")
        if brand == "braun":
            show_df = latest_df[["상품명", "개수", "수량", "가격"]].copy()
            show_df.columns = ["시리즈", "모델명/품번", "색상", "가격"]
            show_df = show_df.sort_values(["시리즈", "가격"], ascending=[True, False])
        else:
            show_df = latest_df[["그룹", "SKU", "개수", "수량", "가격"]].copy()
            show_df.columns = ["그룹", "SKU", "개수", "수량", "가격"]
            show_df = show_df.sort_values(["그룹", "가격"], ascending=[True, False])
        show_df["가격"] = show_df["가격"].apply(fmt_price)
        st.dataframe(show_df, use_container_width=True, height=500)
