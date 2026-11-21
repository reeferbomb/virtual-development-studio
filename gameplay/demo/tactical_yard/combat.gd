extends RefCounted

const MAX_HEALTH := 100
const MAGAZINE_SIZE := 6
const SHOT_INTERVAL := 0.25

var health: int = MAX_HEALTH
var ammo: int = MAGAZINE_SIZE
var reserve: int = 18
var cooldown: float = 0.0

func tick(delta: float) -> void:
	if is_finite(delta) and delta > 0.0:
		cooldown = maxf(0.0, cooldown - delta)

func fire() -> bool:
	if health <= 0 or ammo <= 0 or cooldown > 0.0:
		return false
	ammo -= 1
	cooldown = SHOT_INTERVAL
	return true

func reload() -> bool:
	if health <= 0:
		return false
	var transfer := mini(MAGAZINE_SIZE - ammo, reserve)
	if transfer <= 0:
		return false
	ammo += transfer
	reserve -= transfer
	return true

func damage(amount: int) -> bool:
	if health <= 0 or amount <= 0:
		return false
	health = maxi(0, health - amount)
	return true

func snapshot() -> Dictionary:
	return {"health": health, "ammo": ammo, "reserve": reserve, "cooldown": cooldown}

func restore(data: Dictionary) -> bool:
	if data.size() != 4 or not data.has_all(["health", "ammo", "reserve", "cooldown"]):
		return false
	for key in ["health", "ammo", "reserve"]:
		var value = data[key]
		if not (value is int or value is float) or not is_finite(float(value)) or value < 0 or value > 1000000 or value != floorf(float(value)):
			return false
	if data.health > MAX_HEALTH or data.ammo > MAGAZINE_SIZE:
		return false
	if not (data.cooldown is int or data.cooldown is float) or not is_finite(float(data.cooldown)) or data.cooldown < 0.0 or data.cooldown > SHOT_INTERVAL:
		return false
	health = int(data.health)
	ammo = int(data.ammo)
	reserve = int(data.reserve)
	cooldown = float(data.cooldown)
	return true
