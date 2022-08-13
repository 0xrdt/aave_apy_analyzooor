import calendar
import streamlit as st
from subgrounds.subgrounds import Subgrounds
import pandas as pd
import datetime
import plotly.express as px
import time

st.set_page_config(
	page_title="AAVE APY tool", 
	layout="wide",
)


st.title("AAVE APY Analyzooor")

st.warning("Loading the data may take a while (approximately 30s/month per market)")

st.markdown('check our landing page: [analyzooor.notawizard.xyz](http://analyzooor.notawizard.xyz/)')

wtf = st.expander("WTF?")
wtf.write("""
	The idea of this app is to give you an overview of the historical APYs of any AAVE market in any chain

	- pick the lending protocols and markets that you want to analyze
	- check the data visualizations provided or download the data as csv
	- become an analyzooor!
""")


methodology = st.expander("Technical Details")
methodology.write("""
	The data is provided by [Messari Subgraphs](https://subgraphs.xyz/)

	We query the data for each of the selected lending protocols+markets and cache this data for 24h, then, we process the daily APYs from the selection and provide multiple data visualizations for them
	
	This app is written in Python, using Streamlit, Plotly, Subgrounds and other libs

	You can find the source code of this app [here](https://github.com/0xrdt/aave_apy_analyzooor)
""")

st.header("Initial Parameters")

date_col1, date_col2 = st.columns(2)
start_date = date_col1.date_input('Start date', datetime.date.today()-datetime.timedelta(days=10))
end_date = date_col2.date_input('End date', datetime.date.today())

subgraph_names = {
	'aave-v2-avalanche',
	'aave-v2-ethereum',
	# 'aave-v2-polygon',
	'aave-v3-avalanche',
	'aave-v3-arbitrum',
	'aave-v3-fantom',
	'aave-v3-polygon',
	'aave-v3-optimism',
	'aave-v3-harmony',
}

chosen_subgraph_names = st.multiselect('Select the lending protocols', subgraph_names, default=['aave-v2-ethereum', 'aave-v3-polygon'])


@st.cache(ttl=60*60*24)
def get_markets(subgraph_name):
	sg = Subgrounds()
	subgraph = sg.load_subgraph(f'https://api.thegraph.com/subgraphs/name/messari/{subgraph_name}')

	markets = subgraph.Query.markets(
		orderBy="timestamp",
		orderDirection='desc',
		first=10000,
	)

	# {
	#  markets (first: 1000) {
	#   id
	# 	name
	#   isActive
	#   totalValueLockedUSD
	#   inputToken {
	#     id
	#   }
	#   outputToken {
	#     id
	#   }
	#  } 
	# }

	data = [
		markets.name,
		markets.totalValueLockedUSD,
		markets.id,
	]

	df = sg.query_df(data)
	df['subgraph'] = subgraph_name
	return df


@st.cache(ttl=60*60*24)
def get_markets_from_multiple_subgraphs(subgraph_names):
	list_of_dfs = []

	for subgraph_name in subgraph_names:
		df = get_markets(subgraph_name)
		list_of_dfs.append(df)

	markets_df = pd.concat(list_of_dfs, ignore_index=True)

	markets_df = markets_df[['subgraph', 'markets_name', 'markets_totalValueLockedUSD', 'markets_id']]
	markets_df = (
		markets_df.
		sort_values(by=['markets_totalValueLockedUSD'], ascending=False).
		reset_index(drop=True)
	)

	markets_df['key'] = markets_df['subgraph']+': '+markets_df['markets_name']

	return markets_df


if chosen_subgraph_names:
	st.header("Market Parameters")

	markets_df = get_markets_from_multiple_subgraphs(chosen_subgraph_names).copy()
	if st.checkbox('Show data about markets'):
		st.write(markets_df)

	chosen_markets = st.multiselect(
		'Select the market', 
		list(markets_df['key']),
		default=["aave-v2-ethereum: Aave interest bearing USDC", 
				 "aave-v3-polygon: USD Coin (PoS)"]
	)
	st.write(chosen_markets)

@st.cache(ttl=60*60*24)
def get_rates_by_market(subgraph_name: str, market_ids: list, 
						start_date: datetime.date, end_date: datetime.date):	
	sg = Subgrounds()
	subgraph = sg.load_subgraph(f'https://api.thegraph.com/subgraphs/name/messari/{subgraph_name}')


	market_daily_snapshots = subgraph.Query.marketDailySnapshots(
		orderBy="timestamp",
		orderDirection='desc',
		first=100_000,
		where={
			'timestamp_lte': calendar.timegm(end_date.timetuple()),
			'timestamp_gte': calendar.timegm(start_date.timetuple()),
			'market_in': market_ids
		}
	)

	data = [
		market_daily_snapshots.timestamp,
		market_daily_snapshots.id,
		market_daily_snapshots.market.name,
		market_daily_snapshots.market.id,
		market_daily_snapshots.market.inputToken.symbol,
		market_daily_snapshots.rates.id,
		market_daily_snapshots.rates.rate,
		market_daily_snapshots.rates.type,
		market_daily_snapshots.rates.side
	]

	df = sg.query_df(data)

	return df


def transform_chosen_markets(chosen_markets_df):

	subgraphs = chosen_markets_df[chosen_markets_mask]['subgraph'].unique()

	chosen_markets_dict = {}
	for subgraph in subgraphs:
		mask = chosen_markets_mask & (chosen_markets_df['subgraph'] == subgraph)
		chosen_markets_dict[subgraph] = list(chosen_markets_df[mask]['markets_id'])
	return chosen_markets_dict


@st.cache(ttl=60*60*24, suppress_st_warning=True, allow_output_mutation=True)
def get_rates_from_chosen_markets(chosen_markets_df):

	chosen_markets_dict = transform_chosen_markets(chosen_markets_df)

	list_of_dfs = []
	for subgraph_name, market_ids in chosen_markets_dict.items():
		df = get_rates_by_market(subgraph_name, market_ids, start_date, end_date).copy()
		df['subgraph'] = subgraph_name
		list_of_dfs.append(df)
		pass

	if list_of_dfs:
		rates_df = pd.concat(list_of_dfs, ignore_index=True)
		return rates_df
	else:
		return pd.DataFrame()


if chosen_subgraph_names and chosen_markets:

	st.header("APY Rates")
	st.info("Tip: click on the legend of the plots to filter out some of the colors")

	chosen_markets_mask = markets_df['key'].isin(chosen_markets)
	chosen_markets_df = markets_df[chosen_markets_mask]

	rates_df = get_rates_from_chosen_markets(chosen_markets_df).copy()

	# rates_df.to_pickle('rates_df.pkl')

	rates_df['datetime'] = pd.to_datetime(rates_df['marketDailySnapshots_timestamp'], unit='s')
	rates_df['apy_kind'] = rates_df['marketDailySnapshots_rates_side']+'_'+rates_df['marketDailySnapshots_rates_type']
	rates_df['apy'] = rates_df['marketDailySnapshots_rates_rate']
	rates_df['market'] = rates_df['subgraph']+": "+rates_df['marketDailySnapshots_market_inputToken_symbol']

	if st.checkbox("Show Scatter Plot", value=True):
		fig = px.scatter(
			rates_df, x='datetime', y='apy', 
			facet_row='apy_kind', color='market',
			height=800, trendline='lowess', 
			trendline_options={'frac': 0.3})

		fig.update_yaxes(matches=None, title='APY (%)')
		fig.update_layout(title='APY per market and kind')

		st.plotly_chart(fig, use_container_width=True)

	if st.checkbox("Show Boxplot", value=False):
		fig = px.box(rates_df, y='apy', color='market', facet_row='apy_kind', height=800)
		fig.update_yaxes(matches=None, title='APY')
		fig.update_layout(title='Boxplot of the APY per market and kind')

		st.plotly_chart(fig, use_container_width=True)

	if st.checkbox("Show Histogram", value=False):
		hist_apy_kind = st.selectbox('APY Kind for the histogram', list(rates_df['apy_kind'].unique()))
		hist_market = st.selectbox('Market for the histogram', list(rates_df['market'].unique()))
		mask = (rates_df['apy_kind']==hist_apy_kind) & (rates_df['market']==hist_market)

		fig = px.histogram(rates_df[mask], x='apy', height=400, 
							title=f'Distribution of the APY for {hist_market} - {hist_apy_kind}')

		st.plotly_chart(fig, use_container_width=True)

	if st.checkbox("Show Raw Data"):
		st.write(rates_df)

	# download csv
	csv = st.cache(rates_df.to_csv)(index=False).encode('utf-8')
	st.download_button(
		'Download CSV of the APY data',
		data=csv,
		file_name='rates.csv'
	)
