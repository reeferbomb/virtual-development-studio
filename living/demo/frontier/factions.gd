extends RefCounted
## Independent reputation scores for the two expedition factions.

const DEFAULT_REPUTATIONS := {"settlers": 0, "rangers": 0}
const MIN_REPUTATION := -100
const MAX_REPUTATION := 100
const ALLIED_THRESHOLD := 25
const HOSTILE_THRESHOLD := -25

var _scores := DEFAULT_REPUTATIONS.duplicate()


func configure() -> bool:
	_scores = DEFAULT_REPUTATIONS.duplicate()
	return true


## Unknown factions read as neutral and cannot be adjusted.
func reputation(faction: String) -> int:
	return _scores.get(faction, 0)


func adjust(faction: String, delta: int) -> bool:
	if not _scores.has(faction):
		return false
	var current := reputation(faction)
	# Bound the delta before addition so extreme integer inputs cannot overflow.
	_scores[faction] = current + clampi(delta, MIN_REPUTATION - current, MAX_REPUTATION - current)
	return true


func disposition(faction: String) -> String:
	var score := reputation(faction)
	if score >= ALLIED_THRESHOLD:
		return "allied"
	if score <= HOSTILE_THRESHOLD:
		return "hostile"
	return "neutral"


func snapshot() -> Dictionary:
	return _scores.duplicate()


func restore(state: Dictionary) -> bool:
	if state.size() != DEFAULT_REPUTATIONS.size():
		return false
	var next_scores := {}
	for faction in DEFAULT_REPUTATIONS:
		var value: Variant = state.get(faction)
		if not (value is int or value is float):
			return false
		# JSON decodes integers as floats. Accept only finite whole scores.
		if not is_finite(float(value)) or value < MIN_REPUTATION or value > MAX_REPUTATION:
			return false
		if int(value) != value:
			return false
		next_scores[faction] = int(value)
	_scores = next_scores
	return true
