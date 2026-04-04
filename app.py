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
    m = re.search(r"시리즈\s+(\d+)", str(name))
    if m:
        return "시리즈 " + m.group(1)
    return "기타"


@st.cache_data(ttl=300)
def load_data():
    df = pd.read_csv("data.csv", parse_dates=["Date"])
    df["SKU"] = df["상품명"] + " " + df["개수"].fillna("")
    df["SKU"] = df["SKU"].str.strip()
    if "브랜드" not in df.columns:
        df["브랜드"] = "duracell"
    df["그룹"] = df.apply(
        lambda r: classify_braun_group(r["상품명"]) if r["브랜드"] == "braun"
                  else classify_group(r["상품명"]),
        axis=1,
    )
    # 품절 문자열은 NaN으로 처리해 숫자 연산 가능하게
    df["가격"] = pd.to_numeric(df["가격"], errors="coerce")
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

        # ── 그룹 필터
        if brand == "braun":
            series_list = ["전체"] + sorted(bdf["그룹"].unique().tolist())
            selected_group = st.radio("시리즈", series_list, horizontal=True,
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
            merged = latest_df.merge(prev_df[["itemID", "가격"]], on="itemID", suffixes=("", "_prev"))
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

            def color_delta(val):
                if val > 0: return "color: red"
                elif val < 0: return "color: blue"
                return "color: gray"

            st.dataframe(
                delta_df.style.map(color_delta, subset=["변동"])
                              .format({"전일가": fmt_price, "현재가": fmt_price, "변동": "{:+,}원"}),
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
        st.dataframe(
            show_df.style.format({"가격": fmt_price}),
            use_container_width=True, height=500,
        )
