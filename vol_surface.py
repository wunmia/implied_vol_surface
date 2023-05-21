import urllib.request
import json
import pandas as pd
import datetime
import plotly.express as px
import numpy as np
import time
import plotly.graph_objects as go
from scipy.interpolate import griddata
import os



t0 = time.time()


####Custom Functions#####
def convert_datetime(dt):
    return datetime.datetime.strftime(dt, '%Y-%m-%d')


###MAIN CLASS####
class VolSurface:
    def __init__(self):
        self.base_url = "https://query1.finance.yahoo.com/v7/finance/options/"
        self.opx_type = ["calls", "puts"]
        self.ticker_list = ["AAPL"]#, "AMZN", "GOOG", "META", "NFLX"]

    def scrape_opx_data(self):

        opx_tables = []

        for ticker in self.ticker_list:
            print(f"Gathering Option Data for {ticker}")

            #df columns
            call_strikes = []
            call_price = []
            call_bid = []
            call_ask = []
            call_exp_date = []
            call_last_traded = []
            call_y_iv = []
            pc_opx = []

            url = self.base_url + ticker
            page = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            infile = urllib.request.urlopen(page).read()

            data = json.loads(infile)
            expire_dates = data["optionChain"]["result"][0]['expirationDates']

            for n, date in enumerate(expire_dates):
                url = f"https://query1.finance.yahoo.com/v7/finance/options/{ticker}?date={date}"

                page = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                infile = urllib.request.urlopen(page).read()
                data = json.loads(infile)

                for opx_type in self.opx_type:
                    if n ==0:
                        quote = data["optionChain"]["result"][0]['underlyingSymbol']
                        market_price = data["optionChain"]["result"][0]["quote"]["regularMarketPrice"]
                    option_data = data["optionChain"]["result"][0]['options'][0][opx_type]

                    for option in option_data:
                        try:
                            call_strikes.append(option["strike"])
                            call_price.append(option["lastPrice"])
                            call_bid.append(option["bid"])
                            call_ask.append(option["ask"])
                            call_exp_date.append(option["expiration"])
                            call_last_traded.append(option["lastTradeDate"])
                            call_y_iv.append(option["impliedVolatility"])
                            pc_opx.append(opx_type)
                        except Exception as E:
                            print(f"Bad Option issue: {E}")

            call_exp_date = [datetime.datetime.fromtimestamp(date).date() for date in call_exp_date]
            call_last_traded = [datetime.datetime.fromtimestamp(date).date() for date in call_last_traded]
            call_strikes = [int(strike) for strike in call_strikes]

            try:
                c_options_table = pd.DataFrame(
                    {'strike': call_strikes,
                     "lastPrice": call_price,
                     "bid": call_bid,
                     "ask": call_ask,
                     "expiration": call_exp_date,
                     "lastTradeDate": call_last_traded,
                     "impliedVolatility": call_y_iv,
                     "put/call": pc_opx,
                     "market_price" : market_price,
                     "quote": quote
                     })

                c_options_table = c_options_table[c_options_table["strike"].between(market_price*0.8,market_price*1.2)]
                opx_tables.append(c_options_table)
            except Exception as E:
                print(f"Bad ticker issue: {E}")
                    
        opx_table = pd.concat(opx_tables)

        print(f"Final Options Table")
        print(opx_table.head())

        opx_table["days_last_traded"] = (datetime.datetime.now().date() - opx_table["lastTradeDate"])
        opx_table = opx_table[(opx_table["days_last_traded"]/ np.timedelta64(1, 'D')).astype(int) <= 3]
        opx_table["DTE"] = ((opx_table["expiration"] - datetime.datetime.now().date())/np.timedelta64(1, 'D')).astype(int)
        opx_table = opx_table.reset_index()
        del opx_table["index"]
        self.opx_table = opx_table

        print(f"Time taken to pull options Data: {int(time.time() - t0)}s")

        return opx_table, time.time()


    def surface_graph(self, ticker):

        bright_blue = [[0, '#7DF9FF'], [1, '#7DF9FF']]
        bright_pink = [[0, '#FF007F'], [1, '#FF007F']]
        light_yellow = [[0, '#FFDB58'], [1, '#FFDB58']]

        opx_table = self.opx_table.copy()
        opx_table = opx_table[opx_table["put/call"] == "puts"][opx_table["quote"] == ticker].reset_index()

        mkt_price = opx_table.at[0,"market_price"]

        x = np.array(opx_table["strike"])
        y = np.array(opx_table["DTE"])
        z = np.array(opx_table["impliedVolatility"])

        xi = np.linspace(x.min(), x.max(), 100)
        yi = np.linspace(y.min(), y.max(), 100)


        X, Y = np.meshgrid(xi, yi)
        Z = griddata((x, y), z, (X, Y), method='cubic')

        length_data = len(x)
        zero_pt = pd.Series([0])
        xp = zero_pt.append(opx_table["strike"], ignore_index = True).reset_index(drop = True)
        yp = zero_pt.append(opx_table["DTE"], ignore_index = True).reset_index(drop = True)
        zp = zero_pt.append(opx_table["impliedVolatility"], ignore_index = True).reset_index(drop = True)

        fig = go.Figure(go.Surface(x=xi, y=yi, z=Z, colorscale='Viridis', name="Vol Surface"))
        fig.add_trace(go.Surface(x=xp.apply(lambda x: mkt_price), y=yp, z = np.array([zp]*length_data), colorscale= bright_pink, showscale=False, opacity=0.1, name="ATM Plane"))


        fig.update_layout(title=F"Implied Vol Curve for {ticker}"
                          ,autosize=False,
                          width=1000, height=1000,
                          margin=dict(l=65, r=50, b=65, t=90),
                          scene=dict(
                              xaxis_title='Strike',
                              yaxis_title='DTE',
                              zaxis_title='Implied Vol',
                          ),
                          )

        if not os.path.exists("images"):
            os.mkdir("images")

        fig.write_image(f"images/{ticker}_vol_surface.png")

        fig.show()

    def save_down(self):
        if not os.path.exists("output"):
            os.mkdir("output")

        self.opx_table.to_excel("output/options_table.xlsx")


def main():
    vol_object = VolSurface()
    opx_table, opx_time = vol_object.scrape_opx_data()
    vol_object.save_down()
    vol_object.surface_graph("AAPL")

    print(f"Data visualised in {int(time.time() - opx_time)}s")
    print(f"Script Finished in {int(time.time() - t0)}s")

if __name__ == "__main__":
    main()

