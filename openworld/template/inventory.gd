extends RefCounted
## Unit-capacity inventory. Each recipe produces one item of the same name.

const ITEMS := ["wood", "stone", "fiber", "tool", "bandage"]
const RECIPES := {
	"tool": {"wood": 2, "stone": 1},
	"bandage": {"fiber": 2},
}

var _capacity := 40
var _items: Dictionary = {}


func configure(capacity: int = 40) -> bool:
	if capacity <= 0:
		return false
	_capacity = capacity
	_items.clear()
	return true


func quantity(item: String) -> int:
	return _items.get(item, 0)


func add(item: String, count: int = 1) -> bool:
	if not ITEMS.has(item) or count <= 0:
		return false
	var available := _capacity
	for existing in _items.values():
		available -= int(existing)
	if count > available:
		return false
	_items[item] = quantity(item) + count
	return true


func remove(item: String, count: int = 1) -> bool:
	var current := quantity(item)
	if count <= 0 or count > current:
		return false
	if count == current:
		_items.erase(item)
	else:
		_items[item] = current - count
	return true


func craft(recipe: String) -> bool:
	if not RECIPES.has(recipe):
		return false
	var ingredients: Dictionary = RECIPES[recipe]
	for item in ingredients:
		if quantity(item) < ingredients[item]:
			return false
	# Each recipe consumes at least one unit, so its single output always fits.
	for item in ingredients:
		remove(item, ingredients[item])
	_items[recipe] = quantity(recipe) + 1
	return true


func snapshot() -> Dictionary:
	return {"version": "1", "capacity": _capacity, "items": _items.duplicate()}


func restore(state: Dictionary) -> bool:
	if state.size() != 3 or not state.has_all(["version", "capacity", "items"]):
		return false
	if typeof(state.version) != TYPE_STRING or state.version != "1" or typeof(state.items) != TYPE_DICTIONARY:
		return false
	var capacity := _positive_integer(state.capacity)
	if capacity == 0:
		return false
	var available := capacity
	var restored := {}
	for item in state.items:
		if typeof(item) != TYPE_STRING or not ITEMS.has(item):
			return false
		var count := _positive_integer(state.items[item])
		if count == 0 or count > available:
			return false
		available -= count
		restored[item] = count
	_capacity = capacity
	_items = restored
	return true


func _positive_integer(value: Variant) -> int:
	if typeof(value) == TYPE_INT:
		return maxi(value, 0)
	# Godot's JSON parser decodes numbers as floats. Bound before converting to int64.
	if typeof(value) == TYPE_FLOAT and is_finite(value) and value >= 1.0 and value < 9223372036854775808.0 and value == floor(value):
		return int(value)
	return 0
