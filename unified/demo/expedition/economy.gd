extends RefCounted
## A seeded outpost shop. Buy and sell are always from the player's perspective.

const BASE_PRICES := {"wood": 4, "stone": 6, "fiber": 3, "tool": 12, "bandage": 5}
const MAX_CREDITS := 1_000_000
const MAX_STOCK := 999

var credits: int:
	get:
		return _credits

var _credits := 0
var _seed := 0
var _buy_prices := {}
var _stock := {}


func configure(seed: int, starting_credits: int = 30) -> bool:
	if starting_credits < 0 or starting_credits > MAX_CREDITS:
		return false
	_seed = seed
	_credits = starting_credits
	for item: String in BASE_PRICES:
		var rng := RandomNumberGenerator.new()
		rng.seed = ("%d/shop/%s" % [seed, item]).hash()
		_buy_prices[item] = BASE_PRICES[item] + rng.randi_range(0, 2)
		_stock[item] = rng.randi_range(4, 12)
	return true


func price(item: String, action: String) -> int:
	var buy_price: int = _buy_prices.get(item, 0)
	if action == "buy":
		return buy_price
	if action == "sell":
		@warning_ignore("integer_division")
		return buy_price / 2
	return 0


func stock(item: String) -> int:
	return _stock.get(item, 0)


func trade(inventory: RefCounted, action: String, item: String, count: int = 1) -> bool:
	var unit_price := price(item, action)
	if inventory == null or unit_price <= 0 or count <= 0 or count > MAX_STOCK:
		return false
	var total := unit_price * count
	var on_hand := stock(item)
	# Inventory operations are all-or-nothing. Every shop-side check precedes them.
	if action == "buy":
		if count > on_hand or total > _credits:
			return false
		if not inventory.has_method("add") or not inventory.call("add", item, count):
			return false
		_stock[item] = on_hand - count
		_credits -= total
	else:
		if count > MAX_STOCK - on_hand or total > MAX_CREDITS - _credits:
			return false
		if not inventory.has_method("remove") or not inventory.call("remove", item, count):
			return false
		_stock[item] = on_hand + count
		_credits += total
	return true


func credit(amount: int) -> bool:
	if _stock.is_empty() or amount <= 0 or amount > MAX_CREDITS - _credits:
		return false
	_credits += amount
	return true


func snapshot() -> Dictionary:
	if _stock.is_empty():
		return {}
	# JSON numbers cannot represent all signed 64-bit seeds exactly.
	return {"version": "1", "seed": str(_seed), "credits": _credits, "stock": _stock.duplicate()}


func restore(state: Dictionary) -> bool:
	if _stock.is_empty() or state.size() != 4 or not state.has_all(["version", "seed", "credits", "stock"]):
		return false
	if state.version is not String or state.version != "1" or state.seed is not String or state.seed != str(_seed):
		return false
	if state.stock is not Dictionary or state.stock.size() != BASE_PRICES.size():
		return false
	var restored_credits := _bounded_integer(state.credits, MAX_CREDITS)
	if restored_credits < 0:
		return false
	var restored_stock := {}
	for item: String in BASE_PRICES:
		var count := _bounded_integer(state.stock.get(item), MAX_STOCK)
		if count < 0:
			return false
		restored_stock[item] = count
	_credits = restored_credits
	_stock = restored_stock
	return true


func _bounded_integer(value: Variant, maximum: int) -> int:
	# The JSON decoder returns floats for whole numbers as well as fractions.
	if value is int:
		return value if value >= 0 and value <= maximum else -1
	if value is float and is_finite(value) and value >= 0.0 and value <= maximum and value == floor(value):
		return int(value)
	return -1
