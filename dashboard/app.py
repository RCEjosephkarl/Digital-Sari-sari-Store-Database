"""Digital Sari-Sari Store — Streamlit reporting dashboard.

    streamlit run dashboard/app.py
    # or:  make dashboard

A web front-end over the 3NF PostgreSQL warehouse. Every number is read live
from the database through :mod:`sarisari.reporting` (the same query layer the
analytics notebook uses) — the dashboard never re-implements any business math.

Three report areas, all driven by the shared sidebar filters
(**date range · product group · brand · granularity**):

* **📈 Sales**     — revenue / units / baskets over time, by group and by brand.
* **👥 Customers** — utang (credit) balances, payments and per-customer drill-down.
* **📦 Stock**     — on-hand levels, reorder flags and inventory value.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from sarisari import reporting as R

# -----------------------------------------------------------------------------
# Page setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sari-Sari Store — Reports",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

PESO = "₱"
SEQ = px.colors.qualitative.Set2  # friendly categorical palette


def peso(x: float) -> str:
    return f"{PESO}{x:,.2f}"


def peso_k(x: float) -> str:
    """Compact peso for big headline numbers (₱1.2M / ₱34.5k)."""
    if abs(x) >= 1_000_000:
        return f"{PESO}{x / 1_000_000:,.2f}M"
    if abs(x) >= 1_000:
        return f"{PESO}{x / 1_000:,.1f}k"
    return f"{PESO}{x:,.0f}"


# -----------------------------------------------------------------------------
# Cached data access — engine is a shared resource; queries are cached by args.
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner="Connecting to the warehouse…")
def get_engine():
    return R.get_engine()


@st.cache_data(ttl=600, show_spinner=False)
def dim_products() -> pd.DataFrame:
    return R.load_dim_products(get_engine())


@st.cache_data(ttl=600, show_spinner=False)
def categories() -> list[str]:
    return R.list_categories(get_engine())


@st.cache_data(ttl=600, show_spinner=False)
def bounds() -> tuple[date, date]:
    return R.date_bounds(get_engine())


# Query wrappers: take only hashable primitives so st.cache_data can key on them.
@st.cache_data(ttl=600, show_spinner=False)
def q_kpi(start, end, cats, brands):
    return R.kpi_summary(get_engine(), R.Filters(start, end, cats, brands), dim_products())


@st.cache_data(ttl=600, show_spinner=False)
def q_timeseries(start, end, cats, brands, freq):
    return R.sales_timeseries(get_engine(), R.Filters(start, end, cats, brands), dim_products(), freq)


@st.cache_data(ttl=600, show_spinner=False)
def q_by_category(start, end, cats, brands):
    return R.sales_by_category(get_engine(), R.Filters(start, end, cats, brands), dim_products())


@st.cache_data(ttl=600, show_spinner=False)
def q_by_brand(start, end, cats, brands):
    return R.sales_by_brand(get_engine(), R.Filters(start, end, cats, brands), dim_products())


@st.cache_data(ttl=600, show_spinner=False)
def q_top_products(start, end, cats, brands, n):
    return R.top_products(get_engine(), R.Filters(start, end, cats, brands), dim_products(), n)


@st.cache_data(ttl=600, show_spinner=False)
def q_payment_mix(start, end, cats, brands):
    return R.payment_mix(get_engine(), R.Filters(start, end, cats, brands), dim_products())


@st.cache_data(ttl=600, show_spinner=False)
def q_customer_balances():
    return R.customer_balances(get_engine())


@st.cache_data(ttl=600, show_spinner=False)
def q_customer_directory():
    return R.customer_directory(get_engine())


@st.cache_data(ttl=600, show_spinner=False)
def q_customer_detail(cid):
    return R.customer_detail(get_engine(), cid)


@st.cache_data(ttl=600, show_spinner=False)
def q_customer_ledger(cid):
    return R.customer_ledger(get_engine(), cid)


@st.cache_data(ttl=600, show_spinner=False)
def q_customer_transactions(cid):
    return R.customer_transactions(get_engine(), cid)


@st.cache_data(ttl=600, show_spinner=False)
def q_stock(cats, brands):
    f = R.Filters(bounds()[0], bounds()[1], cats, brands)
    return R.stock_report(get_engine(), f, dim_products())


# -----------------------------------------------------------------------------
# Sidebar — global filters
# -----------------------------------------------------------------------------
def sidebar() -> tuple[date, date, tuple[str, ...], tuple[str, ...], str]:
    st.sidebar.title("🏪 Sari-Sari Reports")
    st.sidebar.caption("Live from the 3NF PostgreSQL warehouse")

    lo, hi = bounds()
    st.sidebar.subheader("🗓️ Time range")
    quick = st.sidebar.radio(
        "Quick range",
        ["All time", "Last 12 months", "Last 3 years", "Year to date", "Custom"],
        index=0,
        horizontal=False,
    )
    if quick == "All time":
        default = (lo, hi)
    elif quick == "Last 12 months":
        default = (max(lo, date(hi.year - 1, hi.month, 1)), hi)
    elif quick == "Last 3 years":
        default = (max(lo, date(hi.year - 3, 1, 1)), hi)
    elif quick == "Year to date":
        default = (max(lo, date(hi.year, 1, 1)), hi)
    else:
        default = (lo, hi)

    picked = st.sidebar.date_input(
        "Date range", value=default, min_value=lo, max_value=hi,
        disabled=(quick != "Custom"),
    )
    if isinstance(picked, (tuple, list)) and len(picked) == 2:
        start, end = picked
    else:
        start, end = default

    freq = st.sidebar.selectbox("Granularity", list(R.FREQ.keys()), index=2)

    st.sidebar.subheader("🏷️ Product filters")
    cats = tuple(st.sidebar.multiselect("Product group", categories(), default=[]))

    dim = dim_products()
    brand_pool = dim[dim["category"].isin(cats)] if cats else dim
    brand_opts = brand_pool["brand"].value_counts().index.tolist()
    brands = tuple(st.sidebar.multiselect("Brand", brand_opts, default=[]))

    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.caption(
        f"Data window: {lo:%b %Y} – {hi:%b %Y}  ·  "
        f"{'all groups' if not cats else f'{len(cats)} group(s)'}, "
        f"{'all brands' if not brands else f'{len(brands)} brand(s)'}"
    )
    return start, end, cats, brands, freq


# -----------------------------------------------------------------------------
# Tab 1 — Sales
# -----------------------------------------------------------------------------
def tab_sales(start, end, cats, brands, freq):
    st.subheader("📈 Sales performance")
    k = q_kpi(start, end, cats, brands)

    c = st.columns(6)
    c[0].metric("Revenue", peso_k(k["revenue"]))
    c[1].metric("Units sold", f"{k['units']:,}")
    c[2].metric("Transactions", f"{k['transactions']:,}")
    c[3].metric("Avg. basket", peso(k["avg_basket"]))
    c[4].metric("Credit share", f"{k['credit_share'] * 100:.1f}%",
                help="Share of revenue sold on utang (credit)")
    c[5].metric("Active customers", f"{k['active_customers']:,}")

    st.divider()

    # --- Trend over time -----------------------------------------------------
    ts = q_timeseries(start, end, cats, brands, freq)
    metric = st.radio("Trend metric", ["Revenue", "Units", "Transactions"],
                      horizontal=True, label_visibility="collapsed")
    col = {"Revenue": "revenue", "Units": "units", "Transactions": "transactions"}[metric]
    if ts.empty:
        st.info("No sales in the selected slice.")
    else:
        fig = px.area(ts, x="period", y=col, markers=(len(ts) <= 60),
                      title=f"{metric} per {freq.lower().rstrip('ly')}"
                            if freq != "Daily" else f"{metric} per day")
        fig.update_traces(line_color="#2a9d8f", fillcolor="rgba(42,157,143,0.15)")
        fig.update_layout(margin=dict(t=50, b=0, l=0, r=0), height=340,
                          xaxis_title=None, yaxis_title=metric)
        st.plotly_chart(fig, use_container_width=True)

    # --- Group + payment mix -------------------------------------------------
    left, right = st.columns([3, 2])
    with left:
        cat = q_by_category(start, end, cats, brands)
        if not cat.empty:
            fig = px.bar(cat.sort_values("revenue"), x="revenue", y="category",
                         orientation="h", color="category", color_discrete_sequence=SEQ,
                         title="Revenue by product group", text_auto=".2s")
            fig.update_layout(showlegend=False, height=320, margin=dict(t=50, b=0, l=0, r=0),
                              xaxis_title="Revenue (₱)", yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
    with right:
        pm = q_payment_mix(start, end, cats, brands)
        if not pm.empty:
            fig = px.pie(pm, names="payment_type", values="revenue", hole=0.55,
                         title="Cash vs. credit (revenue)",
                         color="payment_type",
                         color_discrete_map={"cash": "#264653", "credit": "#e76f51"})
            fig.update_layout(height=320, margin=dict(t=50, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    # --- Brands + top SKUs ---------------------------------------------------
    left, right = st.columns(2)
    with left:
        br = q_by_brand(start, end, cats, brands).head(15)
        if not br.empty:
            fig = px.bar(br.sort_values("revenue"), x="revenue", y="brand",
                         orientation="h", title="Top 15 brands by revenue",
                         color="revenue", color_continuous_scale="Teal", text_auto=".2s")
            fig.update_layout(height=460, margin=dict(t=50, b=0, l=0, r=0),
                              coloraxis_showscale=False, xaxis_title="Revenue (₱)",
                              yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("**Top-selling products**")
        tp = q_top_products(start, end, cats, brands, 15)
        st.dataframe(
            tp, hide_index=True, height=460, width="stretch",
            column_config={
                "name": "Product",
                "category": "Group",
                "brand": "Brand",
                "revenue": st.column_config.NumberColumn("Revenue", format="₱%.0f"),
                "units": st.column_config.NumberColumn("Units", format="%d"),
                "transactions": st.column_config.NumberColumn("Txns", format="%d"),
            },
        )
        st.download_button("⬇️ Download top products (CSV)",
                           tp.to_csv(index=False).encode(), "top_products.csv",
                           "text/csv", width="stretch")


# -----------------------------------------------------------------------------
# Tab 2 — Customers
# -----------------------------------------------------------------------------
def tab_customers():
    st.subheader("👥 Customers & utang (credit)")
    cb = q_customer_balances()

    outstanding = float(cb["balance"].clip(lower=0).sum())
    with_balance = int((cb["balance"] > 0.005).sum())
    over_limit = int((cb["credit_available"] < -0.005).sum())
    credit_extended = float(cb["credit_limit"].sum())

    c = st.columns(4)
    c[0].metric("Outstanding utang", peso_k(outstanding))
    c[1].metric("Customers owing", f"{with_balance:,}",
                help="Customers with a positive running balance")
    c[2].metric("Over credit limit", f"{over_limit:,}",
                help="Balance exceeds the customer's credit limit")
    c[3].metric("Total credit extended", peso_k(credit_extended))
    st.divider()

    left, right = st.columns(2)
    with left:
        top = cb[cb["balance"] > 0].head(15)
        if not top.empty:
            top = top.assign(who=top["nickname"].fillna(top["full_name"]))
            fig = px.bar(top.sort_values("balance"), x="balance", y="who",
                         orientation="h", title="Top 15 debtors (running utang)",
                         color="balance", color_continuous_scale="Reds", text_auto=".2s")
            fig.update_layout(height=420, margin=dict(t=50, b=0, l=0, r=0),
                              coloraxis_showscale=False, xaxis_title="Balance (₱)",
                              yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
    with right:
        owing = cb[cb["balance"] > 0]
        if not owing.empty:
            fig = px.histogram(owing, x="balance", nbins=40,
                               title="Distribution of outstanding balances")
            fig.update_traces(marker_color="#e76f51")
            fig.update_layout(height=420, margin=dict(t=50, b=0, l=0, r=0),
                              xaxis_title="Balance (₱)", yaxis_title="Customers")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Customer ledger")
    table_tab, detail_tab = st.tabs(["📋 All customers", "🔍 Single customer"])

    with table_tab:
        only_owing = st.toggle("Show only customers with a balance", value=True)
        view = cb[cb["balance"] > 0] if only_owing else cb
        st.dataframe(
            view, hide_index=True, width="stretch", height=430,
            column_config={
                "customer_id": "ID",
                "full_name": "Name",
                "nickname": "Palayaw",
                "credit_limit": st.column_config.NumberColumn("Limit", format="₱%.0f"),
                "total_utang": st.column_config.NumberColumn("Charged", format="₱%.0f"),
                "total_paid": st.column_config.NumberColumn("Paid", format="₱%.0f"),
                "balance": st.column_config.NumberColumn("Balance", format="₱%.2f"),
                "credit_available": st.column_config.NumberColumn("Headroom", format="₱%.0f"),
                "n_transactions": st.column_config.NumberColumn("Txns", format="%d"),
                "lifetime_spend": st.column_config.NumberColumn("Lifetime", format="₱%.0f"),
                "last_purchase": st.column_config.DateColumn("Last buy"),
            },
        )
        st.download_button("⬇️ Download customer balances (CSV)",
                           view.to_csv(index=False).encode(), "customer_balances.csv",
                           "text/csv")

    with detail_tab:
        directory = q_customer_directory()
        labels = directory.apply(
            lambda r: f"#{r.customer_id} · {r.full_name}"
            + (f' "{r.nickname}"' if pd.notna(r.nickname) else ""), axis=1
        ).tolist()
        idx = st.selectbox("Pick a customer", range(len(labels)),
                           format_func=lambda i: labels[i])
        cid = int(directory.iloc[idx]["customer_id"])

        d = q_customer_detail(cid)
        if d:
            m = st.columns(5)
            m[0].metric("Balance (utang)", peso(float(d["balance"])))
            m[1].metric("Credit limit", peso(float(d["credit_limit"])))
            m[2].metric("Headroom", peso(float(d["credit_available"])))
            m[3].metric("Lifetime spend", peso_k(float(d["lifetime_spend"])))
            m[4].metric("Transactions", f"{int(d['n_transactions']):,}")

        ledger = q_customer_ledger(cid)
        lcol, rcol = st.columns([3, 2])
        with lcol:
            if ledger.empty:
                st.info("This customer has no utang activity (cash buyer).")
            else:
                fig = px.line(ledger, x="entry_date", y="running_balance",
                              markers=True, title="Running utang balance over time")
                fig.update_traces(line_color="#e76f51")
                fig.update_layout(height=320, margin=dict(t=50, b=0, l=0, r=0),
                                  xaxis_title=None, yaxis_title="Balance (₱)")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Charges (credit sales) raise the line; payments lower it — "
                           "the digital version of the *utang* notebook page.")
        with rcol:
            st.markdown("**Recent transactions**")
            st.dataframe(
                q_customer_transactions(cid), hide_index=True, height=300,
                width="stretch",
                column_config={
                    "transaction_id": "Txn",
                    "date": st.column_config.DateColumn("Date"),
                    "payment_type": "Type",
                    "items": st.column_config.NumberColumn("Items", format="%d"),
                    "amount": st.column_config.NumberColumn("Amount", format="₱%.2f"),
                },
            )

        if not ledger.empty:
            with st.expander("Full utang ledger (charges & payments)"):
                st.dataframe(
                    ledger, hide_index=True, width="stretch",
                    column_config={
                        "entry_date": st.column_config.DateColumn("Date"),
                        "entry_type": "Type",
                        "reference": "Ref",
                        "debit": st.column_config.NumberColumn("Charge", format="₱%.2f"),
                        "credit": st.column_config.NumberColumn("Payment", format="₱%.2f"),
                        "running_balance": st.column_config.NumberColumn("Balance", format="₱%.2f"),
                    },
                )


# -----------------------------------------------------------------------------
# Tab 3 — Stock
# -----------------------------------------------------------------------------
def tab_stock(cats, brands):
    st.subheader("📦 Stock & inventory")
    stock = q_stock(cats, brands)
    if stock.empty:
        st.info("No products match the current filters.")
        return

    c = st.columns(4)
    c[0].metric("SKUs", f"{len(stock):,}")
    c[1].metric("Units on hand", f"{int(stock['on_hand'].sum()):,}")
    c[2].metric("Inventory value", peso_k(float(stock["stock_value"].sum())),
                help="On-hand units × current selling price")
    c[3].metric("Needs reorder", f"{int(stock['needs_reorder'].sum()):,}",
                help="On-hand at or below the product's reorder level")
    st.divider()

    left, right = st.columns(2)
    with left:
        by_cat = (stock.groupby("category", as_index=False)["stock_value"].sum()
                  .sort_values("stock_value"))
        fig = px.bar(by_cat, x="stock_value", y="category", orientation="h",
                     title="Inventory value by group", color="category",
                     color_discrete_sequence=SEQ, text_auto=".2s")
        fig.update_layout(showlegend=False, height=340, margin=dict(t=50, b=0, l=0, r=0),
                          xaxis_title="Value (₱)", yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        lowest = stock.nsmallest(15, "on_hand")
        fig = px.bar(lowest.sort_values("on_hand", ascending=False),
                     x="on_hand", y="product", orientation="h",
                     title="15 lowest-stock products", color="on_hand",
                     color_continuous_scale="OrRd_r", text_auto=True)
        fig.update_layout(height=340, margin=dict(t=50, b=0, l=0, r=0),
                          coloraxis_showscale=False, xaxis_title="On hand",
                          yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Stock report")
    cc = st.columns([1, 1, 2])
    only_reorder = cc[0].toggle("Only items needing reorder", value=False)
    show_drift = cc[1].toggle("Show trigger-vs-derived drift", value=False,
                              help="Reconcile the maintained stock_on_hand column "
                                   "against the strictly-derived view value")
    view = stock[stock["needs_reorder"]] if only_reorder else stock
    cols = ["product", "category", "brand", "unit", "on_hand", "reorder_level",
            "total_restocked", "total_sold", "current_price", "stock_value"]
    if show_drift:
        view = view.assign(drift=view["on_hand"] - view["maintained_on_hand"])
        cols += ["maintained_on_hand", "drift"]

    st.dataframe(
        view[cols], hide_index=True, width="stretch", height=430,
        column_config={
            "product": "Product",
            "category": "Group",
            "brand": "Brand",
            "unit": "Unit",
            "on_hand": st.column_config.NumberColumn("On hand", format="%d"),
            "reorder_level": st.column_config.NumberColumn("Reorder @", format="%d"),
            "total_restocked": st.column_config.NumberColumn("In", format="%d"),
            "total_sold": st.column_config.NumberColumn("Out", format="%d"),
            "current_price": st.column_config.NumberColumn("Price", format="₱%.2f"),
            "stock_value": st.column_config.NumberColumn("Value", format="₱%.0f"),
            "maintained_on_hand": st.column_config.NumberColumn("Maintained", format="%d"),
            "drift": st.column_config.NumberColumn("Drift", format="%d"),
        },
    )
    if show_drift:
        drift = int((view["on_hand"] != view["maintained_on_hand"]).sum())
        (st.success if drift == 0 else st.warning)(
            f"Reconciliation: {drift} product(s) where the trigger-maintained "
            "column disagrees with the derived view."
        )
    st.download_button("⬇️ Download stock report (CSV)",
                       view[cols].to_csv(index=False).encode(), "stock_report.csv",
                       "text/csv")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    try:
        start, end, cats, brands, freq = sidebar()
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        st.error(
            "Could not reach the database. Run the pipeline first "
            "(`make pipeline`), then reload.\n\n"
            f"```\n{exc}\n```"
        )
        st.stop()

    st.title("🏪 Digital Sari-Sari Store — Reports")
    st.caption(
        f"Showing **{start:%d %b %Y} → {end:%d %b %Y}**"
        + (f"  ·  groups: {', '.join(cats)}" if cats else "")
        + (f"  ·  brands: {', '.join(brands)}" if brands else "")
    )

    sales, customers, stock = st.tabs(["📈 Sales", "👥 Customers", "📦 Stock"])
    with sales:
        tab_sales(start, end, cats, brands, freq)
    with customers:
        tab_customers()
    with stock:
        tab_stock(cats, brands)


if __name__ == "__main__":
    main()
