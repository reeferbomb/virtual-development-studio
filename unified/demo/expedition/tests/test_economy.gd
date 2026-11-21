extends SceneTree

const Economy = preload("res://economy.gd")
const Inventory = preload("res://inventory.gd")

var failures := 0


func check(condition: bool, detail: String) -> void:
	if not condition:
		printerr("FAIL ", detail)
		failures += 1


func reject_trade(shop: Economy, pack: Inventory, action: String, item: String, count: int) -> void:
	var wallet_before := shop.snapshot()
	var pack_before := pack.snapshot()
	check(not shop.trade(pack, action, item, count), "reject %s %s x%d" % [action, item, count])
	check(shop.snapshot() == wallet_before and pack.snapshot() == pack_before, "rejected trade preserves both sides")


func test_trades() -> void:
	var shop := Economy.new()
	var pack := Inventory.new()
	check(shop.snapshot().is_empty() and shop.price("wood", "buy") == 0, "shop awaits seed")
	check(not shop.credit(1) and not shop.trade(pack, "sell", "wood"), "no commerce before setup")
	check(shop.configure(42) and shop.credits == 30, "default wallet")
	var initial := shop.snapshot()
	var twin := Economy.new()
	check(twin.configure(42) and twin.snapshot() == initial, "seed reproduces stock")
	for item: String in Inventory.ITEMS:
		var buy := shop.price(item, "buy")
		var sell := shop.price(item, "sell")
		check(buy > sell and sell > 0 and shop.stock(item) > 0, "positive spread and initial stock for " + item)
		check(twin.price(item, "buy") == buy and twin.price(item, "sell") == sell, "repeatable prices for " + item)
	check(shop.price("ore", "buy") == 0 and shop.price("wood", "gift") == 0, "unknown quotes")
	check(shop.price("tool", "sell") <= 2 * shop.price("wood", "buy") + shop.price("stone", "buy"), "tool recipe spread")
	check(shop.price("bandage", "sell") <= 2 * shop.price("fiber", "buy"), "bandage recipe spread")
	check(not shop.configure(9, -1) and not shop.configure(9, Economy.MAX_CREDITS + 1) and shop.snapshot() == initial, "invalid setup is atomic")

	var wood_buy := shop.price("wood", "buy")
	var wood_sell := shop.price("wood", "sell")
	check(pack.configure(2) and shop.trade(pack, "buy", "wood", 2), "buy two wood")
	check(shop.credits == 30 - 2 * wood_buy and pack.quantity("wood") == 2 and shop.stock("wood") == initial.stock.wood - 2, "purchase exact units and price")
	reject_trade(shop, pack, "buy", "wood", 1) # Full pack with enough funds.
	reject_trade(shop, pack, "sell", "wood", 3)
	reject_trade(shop, pack, "sell", "stone", 1)
	for count in [0, -1, 9223372036854775807]:
		reject_trade(shop, pack, "buy", "wood", count)
		reject_trade(shop, pack, "sell", "wood", count)
	reject_trade(shop, pack, "buy", "ore", 1)
	reject_trade(shop, pack, "gift", "wood", 1)
	check(shop.trade(pack, "sell", "wood", 2), "sell two wood")
	check(shop.credits == 30 - 2 * (wood_buy - wood_sell) and shop.snapshot().stock == initial.stock and pack.quantity("wood") == 0, "round trip restores goods at a loss")
	var before := shop.snapshot()
	check(not shop.trade(null, "buy", "wood") and not shop.trade(RefCounted.new(), "buy", "wood") and shop.snapshot() == before, "missing inventory")
	check(shop.configure(42, 0), "empty wallet")
	reject_trade(shop, pack, "buy", "wood", 1)
	check(pack.add("tool") and shop.trade(pack, "sell", "tool") and pack.quantity("tool") == 0 and shop.credits == shop.price("tool", "sell"), "sell crafted tool from empty wallet")

	check(shop.configure(42, 2_000) and pack.configure(2_000), "funded shop")
	var available := shop.stock("fiber")
	check(shop.trade(pack, "buy", "fiber", available) and shop.stock("fiber") == 0, "buy last fiber")
	reject_trade(shop, pack, "buy", "fiber", 1)
	check(shop.trade(pack, "sell", "fiber") and shop.stock("fiber") == 1, "sale restocks shop")
	check(pack.add("fiber", Economy.MAX_STOCK) and shop.trade(pack, "sell", "fiber", Economy.MAX_STOCK - 1), "fill stock limit")
	reject_trade(shop, pack, "sell", "fiber", 1)


func test_rewards_and_restore() -> void:
	var shop := Economy.new()
	var pack := Inventory.new()
	var world_seed := 9223372036854775807
	check(shop.configure(world_seed, Economy.MAX_CREDITS - 1) and shop.credit(1), "reward exactly up to balance limit")
	check(shop.credits == Economy.MAX_CREDITS and pack.add("tool"), "wallet at limit")
	reject_trade(shop, pack, "sell", "tool", 1)
	for amount in [0, -1, 1, 9223372036854775807]:
		check(not shop.credit(amount) and shop.credits == Economy.MAX_CREDITS, "reject invalid or overflowing reward")
	check(shop.trade(pack, "buy", "bandage") and shop.credit(2), "stage reward and stock change")
	var saved := shop.snapshot()
	var parsed: Dictionary = JSON.parse_string(JSON.stringify(saved))
	var resumed := Economy.new()
	check(not resumed.restore(parsed), "require pinned seed before restore")
	check(resumed.configure(world_seed) and resumed.restore(parsed) and resumed.snapshot() == saved, "JSON round trip including 64-bit seed")
	parsed.stock.wood = -9
	resumed.snapshot().stock.fiber = -2
	check(resumed.snapshot() == saved, "detached stock dictionaries")
	var foreign := Economy.new()
	check(foreign.configure(world_seed - 1) and not resumed.restore(foreign.snapshot()) and resumed.snapshot() == saved, "reject adjacent foreign 64-bit seed")
	for field: String in ["version", "seed", "credits", "stock"]:
		var missing := saved.duplicate(true)
		missing.erase(field)
		check(not resumed.restore(missing) and resumed.snapshot() == saved, "missing " + field)
	for key in ["extra", "version", "seed", "credits", "stock"]:
		var malformed := saved.duplicate(true)
		malformed[key] = true
		check(not resumed.restore(malformed) and resumed.snapshot() == saved, "invalid " + key)
	for invalid in [null, -1, 5.5, INF, NAN, "2", false, Economy.MAX_CREDITS + 1]:
		var malformed := saved.duplicate(true)
		malformed.credits = invalid
		check(not resumed.restore(malformed) and resumed.snapshot() == saved, "invalid wallet")
	for invalid in [null, -1, 1.5, INF, NAN, "4", true, Economy.MAX_STOCK + 1]:
		var malformed := saved.duplicate(true)
		malformed.credits = 0
		malformed.stock.tool = invalid
		check(not resumed.restore(malformed) and resumed.snapshot() == saved, "invalid stock leaves wallet and stock unchanged")
	var bad_roster := saved.duplicate(true)
	bad_roster.stock.erase("stone")
	bad_roster.stock.ore = 5
	check(not resumed.restore(bad_roster) and resumed.snapshot() == saved, "unknown replacement item")
	check(resumed.configure(world_seed) and resumed.credits == 30, "start a fresh market")


func _initialize() -> void:
	test_trades()
	test_rewards_and_restore()
	print("Economy assertions finished, failures=", failures)
	quit(int(failures != 0))
