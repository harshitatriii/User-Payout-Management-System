# Business Constants

from decimal import Decimal

#10% advance of a total sale earning
ADVANCE_RATE = Decimal("0.10")

#Only 1 withdrawal in 24 hours
WITHDRAWAL_COOLDOWN_HOURS = 24

#Quantized to 2 places (in paise)
MONEY_QUANTIZE = Decimal("0.01")