import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="쿠팡 가격 트래커", page_icon="📦", layout="wide")

def classify_group(name):
    name = str(name)
    if "울트라" in name:
        return "울트라"
    if "디럭스" in name:
        return "디럭스"
    if "알카라인" in name and ("AA" in name or "AAA" in name):
        return "오리지널"
    if any(x in name for x in ["2032", "2025", "2016"]):
        return "리튬코인"
    if any(x in name for x in ["C형", "D형", "9V"]):
        return "C/D/9V"
    return "기타특수"

@st.cache_data(ttl=300)
def load_data():
    df = pd.read_csv("data.csv", parse_dates=["Date"])
    df["SKU"] = df["상품명"] + " " + df["개수"]
    df["그룹"] = df["상품명"].apply(classify_group)
    return df

df = load_data()
dates = sorted(df["Date"].dt.date.unique())
latest = max(dates)
prev = dates[-2] if len(dates) >= 2 else None

# ── 헤더
st.title("📦 쿠팡 가격 트래킹 대시보드")
st.caption(f"마지막 업데이트: {latest}")

# ── 그룹 필터 (상단 탭)
groups = ["전체", "오리지널", "울트라", "디럭스", "C/D/9V", "리튬코인", "기타특수"]
selected_group = st.radio("상품 그룹", groups, horizontal=True, label_visibility="collapsed")

def filter_by_group(dataframe):
    if selected_group == "전체":
        return dataframe
    return dataframe[dataframe["그룹"] == selected_group]

st.divider()

# ── 요약 지표
latest_df = filter_by_group(df[df["Date"].dt.date == latest].copy())
col1, col2, col3, col4 = st.columns(4)
col1.metric("추적 상품 수", f"{len(latest_df)}개")

if prev:
    prev_df = df[df["Date"].dt.date == prev].copy()
    merged = latest_df.merge(prev_df[["itemID","가격"]], on="itemID", suffixes=("","_prev"))
    merged["변동"] = merged["가격"] - merged["가격_prev"]
    up = (merged["변동"] > 0).sum()
    down = (merged["변동"] < 0).sum()
    col2.metric("가격 인상", f"{up}개", delta=f"+{up}", delta_color="inverse")
    col3.metric("가격 인하", f"{down}개", delta=f"-{down}", delta_color="normal")
    col4.metric("변동 없음", f"{len(merged)-up-down}개")
else:
    col2.metric("가격 인상", "-")
    col3.metric("가격 인하", "-")
    col4.metric("변동 없음", "-")

st.divider()

# ── 전일 대비 변동 표
st.subheader("📊 전일 대비 가격 변동")
if prev:
    delta_df = merged[["SKU","개수","수량","가격_prev","가격","변동"]].copy()
    delta_df.columns = ["SKU","개수","수량","전일가","현재가","변동"]
    delta_df = delta_df.sort_values("변동")

    def color_delta(val):
        if val > 0: return "color: red"
        elif val < 0: return "color: blue"
        return "color: gray"

    st.dataframe(
        delta_df.style.map(color_delta, subset=["변동"])
                      .format({"전일가": "{:,}원", "현재가": "{:,}원", "변동": "{:+,}원"}),
        use_container_width=True, height=400
    )
else:
    st.info("비교할 이전 날짜 데이터가 없습니다.")

st.divider()

# ── 상품별 가격 추이
st.subheader("📈 상품별 가격 추이")
filtered_df = filter_by_group(df)
skus = sorted(filtered_df["SKU"].unique())
selected = st.multiselect("상품 선택", skus, default=skus[:5])

if selected:
    chart_df = filtered_df[filtered_df["SKU"].isin(selected)]
    fig = px.line(
        chart_df, x="Date", y="가격", color="SKU",
        markers=True, labels={"가격": "가격 (원)", "Date": "날짜"}
    )
    fig.update_layout(height=450, legend=dict(orientation="h", yanchor="bottom", y=1.02))
    fig.update_yaxes(tickformat=",")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── 현재 가격 전체 테이블
st.subheader("📋 현재 가격 전체 목록")
show_df = latest_df[["그룹","SKU","개수","수량","가격"]].copy()
show_df = show_df.sort_values(["그룹","가격"], ascending=[True, False])
st.dataframe(
    show_df.style.format({"가격": "{:,}원"}),
    use_container_width=True, height=500
)
