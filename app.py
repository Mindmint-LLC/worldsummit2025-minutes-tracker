
import os
import streamlit as st
from dbharbor.bigquery import SQL
# from streamlit_authentication.google_oauth import authenticate
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import datetime as dt

START_DATE = os.getenv('START_DATE')
TRACKING_URL = os.getenv('TRACKING_URL')
REFRESH_MINS= int(os.getenv('REFRESH_MINS', 1))
TITLE = os.getenv('TITLE', 'Mastermind Business System Sales')


#%%

def StyleDF(df):
    fmt_cash = lambda x: '-' if pd.isna(x) or int(x) == 0 else '${:,.0f}'.format(int(x)) if int(x) >= 0 else '$({:,.0f})'.format(abs(int(x)))
    fmt_int = lambda x: '-' if pd.isna(x) or int(x) == 0 else '{:,.0f}'.format(int(x)) if int(x) >= 0 else '({:,.0f})'.format(abs(int(x)))

    clmn_format_dict = {}
    for clmn in ['PIF Cash', '3 Pay Cash', 'Total Cash']:
        clmn_format_dict[clmn] = fmt_cash
    for clmn in ['PIF Sales', '3 Pay Sales', 'Total Sales']:
        clmn_format_dict[clmn] = fmt_int


    dfg_all_formatted = df.style\
        .hide(axis="index")\
        .set_properties(**{'text-align': 'left'})\
        .set_properties(**{'font-size': '18px;'})\
        .set_properties(**{'font-family': 'Century Gothic, sans-serif;'})\
        .set_properties(**{'padding': '3px 20px 3px 5px;'})\
        .set_table_styles([
            # Column Headers
            {
                'selector': 'thead th',
                'props': 'background-color: #FFFFFF;\
                    color: #305496;\
                    border-bottom: 2px solid #305496;\
                    text-align: left;\
                    font-size: 20px;\
                    font-family: Century Gothic, sans-serif;\
                    padding: 0px 20px 0px 5px;'
            },
            # Last Column Header
            {
                'selector': 'thead th:last-child',
                'props': 'color: black;'
            },
            # Even Rows
            {
                'selector': 'tbody tr:nth-child(even)',
                'props': 'background-color: white;\
                    color: black;'
            },
            # Odd Rows
            {
                'selector': 'tbody tr:nth-child(odd)',
                'props': 'background-color: #D9E1F2;'
            },
            # Last Row
            {
                'selector': 'tbody tr:last-child td',
                'props': 'font-weight: bold;\
                    border-top: 2px solid #305496;'
            },
            # First Column
            {
                'selector': 'tbody td:first-child',
                'props': 'border-right: 2px solid #305496;'
            },
            # Last Column
            {
                'selector': 'tbody td:last-child',
                'props': 'font-weight: bold;\
                    border-left: 2px solid #305496;'
            },
            ])\
        .format(clmn_format_dict)
    html = dfg_all_formatted.to_html()
    html = html.replace('<style type="text/css">', '<style type="text/css">\ntable {\n\tborder-spacing: 0;\n}')
    return html


@st.cache_data(ttl=REFRESH_MINS * 59)
def GetData():
    con = SQL()
    sql = f'''
        with mysql as (
            select *
            FROM EXTERNAL_QUERY("bbg-platform.us.mastermind", """

                SELECT email
                    , dt
                    , product
                    , amount
                FROM kbb_evergreen.tracking_orders d
                WHERE d.dt >= "{START_DATE}"
                    and `status` = "paid"
                    and d.product in (
                        "Mastermind Business System",
                        "Mastermind Business System 3 Pay"
                    );
        
            """)
        )

        , stripe as (
      select s.email
        , i.invoice_dt as dt
        , i.product
        , i.amount_due as amount
      from `bbg-platform.analytics_stage.int_stripe__invoice` i
        join `bbg-platform.analytics_stage.int_stripe__subscription_history` s
          on i.subscription_id = s.subscription_id
            join `bbg-platform.analytics.dim_products` p
            on i.product = p.product
            and p.sub_category = '997 membership'
        where cast(invoice_dt as date) >= "{START_DATE}"
            and invoice_status in ('paid')
        )

        , final as (
        select m.*
        from mysql m
        where m.dt >= date_add(current_datetime(), interval -2 day)
            and m.email not in (
            select s.email
            from stripe s
        )

        union all

        select * from stripe
        )

        select cast(m.dt as date) as `Date`
            , sum(case when m.product in ("Mastermind Business System", "997_yearly", "mm_annual_997_1") then 1 else 0 end) as `PIF Sales`
            , sum(case when m.product in ("Mastermind Business System", "997_yearly") then m.amount else 0 end) as `PIF Cash`
            , sum(case when m.product in ("Mastermind Business System 3 Pay", "yearly_3_payment_plan_380_per_month") then 1 else 0 end) as `3 Pay Sales`
            , sum(case when m.product in ("Mastermind Business System 3 Pay", "yearly_3_payment_plan_380_per_month") then m.amount else 0 end) as `3 Pay Cash`
            , count(*) as `Total Sales`
            , sum(amount) as `Total Cash`
        from final m
        where analytics.fnEmail_IsTest(m.email) = False
        group by all
        order by 1
    '''
    df = con.read(sql)
    df = df.set_index('Date')
    dfg_aggr = df.sum(axis=0, numeric_only=True)
    dfg_aggr = pd.DataFrame(dfg_aggr).T
    dfg_aggr.index = ['Total']
    df = pd.concat([df, dfg_aggr])
    df = df.reset_index(names=['Date'])
    styled_html = StyleDF(df)

    last_update = (dt.datetime.now() + dt.timedelta(hours=-7)).strftime('%m/%d/%Y, %H:%M:%S')
    return styled_html, last_update


#%% Streamlit App

st.set_page_config(layout="wide")


# @authenticate
def Dashboard():
    st_autorefresh(interval=REFRESH_MINS * 60 * 1000, key="fizzbuzzcounter") # milliseconds

    st.title(TITLE)

    st.markdown('<br><br>', unsafe_allow_html=True)
    
    st.subheader('Mastermind Business System Sales')
    styled_html, last_update = GetData()
    st.write(styled_html, unsafe_allow_html=True)
    st.markdown(f'Last Update: {last_update}<br>Updates Every {REFRESH_MINS} Minute(s) Automatically', unsafe_allow_html=True)

    st.markdown('<br>', unsafe_allow_html=True)
    st.components.v1.iframe(TRACKING_URL, width=800, height=500)
    st.markdown(f'Updates Every Hour Automatically', unsafe_allow_html=True)

Dashboard()