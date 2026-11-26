"""Chi bao dinh luong co ban: SMA, RSI, ATR, volatility.
Ly thuyet do Yuling nghien cuu, cai dat do LJ/Kel thuc hien."""


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    return sum(trs[-period:]) / period


def volatility(values, period=20):
    if len(values) < period:
        return None
    mean = sum(values[-period:]) / period
    var = sum((v - mean) ** 2 for v in values[-period:]) / period
    return var ** 0.5
