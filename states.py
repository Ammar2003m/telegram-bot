from aiogram.fsm.state import State, StatesGroup


class EditRate(StatesGroup):
    currency = State()
    value    = State()


class EditBalance(StatesGroup):
    user_id = State()
    amount  = State()


class FindUser(StatesGroup):
    user_id = State()


class Broadcast(StatesGroup):
    message = State()


class AddUsername(StatesGroup):
    username = State()
    type_    = State()
    price    = State()


class DepositManual(StatesGroup):
    amount  = State()
    receipt = State()


class DepositUSDT(StatesGroup):
    amount = State()


class BuyPremium(StatesGroup):
    username = State()


class BuyStars(StatesGroup):
    username = State()


class BuyFake(StatesGroup):
    link = State()


class BuyNetflix(StatesGroup):
    email = State()


class CouponState(StatesGroup):
    code = State()


class AddCoupon(StatesGroup):
    code        = State()
    discount    = State()
    usage_limit = State()
