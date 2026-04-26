import json
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.rewe.de/"
CITY_FILE = Path("city_name.txt")
OUTPUT_FILE = Path("rewe.txt")
PROGRESS_FILE = Path("rewe_progress.json")


def random_pause(min_seconds: float = 0.6, max_seconds: float = 1.6) -> None:
	"""Pause for a random short duration to avoid aggressive request patterns."""
	time.sleep(random.uniform(min_seconds, max_seconds))


def normalize_spaces(value: str) -> str:
	return re.sub(r"\s+", " ", value).strip()


def get_city_search_term(city_name: str) -> str:
	"""Use the first word as search term, e.g. 'Frankfurt am Main' -> 'Frankfurt'."""
	normalized = normalize_spaces(city_name)
	if not normalized:
		return city_name
	return normalized.split(" ", 1)[0]


def wait_until(
	check_fn,
	description: str,
	check_interval_seconds: float = 3.0,
	log_every_attempts: int = 4,
) -> None:
	"""Keep polling until check_fn returns True, allowing manual intervention on the page."""
	attempt = 0
	while True:
		attempt += 1
		try:
			if check_fn():
				if attempt > 1:
					print(f"检测到页面已恢复: {description}，继续运行")
				return
		except Exception:
			# Ignore transient page/DOM errors and continue polling.
			pass

		if attempt == 1 or attempt % log_every_attempts == 0:
			print(
				f"等待页面满足条件: {description}。如果出现 Cookie 通知或验证码，请手动处理，脚本会自动继续..."
			)
		time.sleep(check_interval_seconds)


def extract_market_count(summary_text: str) -> int | None:
	"""Parse summary text like '266 Märkte gefunden' and return 266."""
	match = re.search(r"([\d\.]+)\s+Märkte\s+gefunden", summary_text, flags=re.IGNORECASE)
	if not match:
		return None
	count_text = match.group(1).replace(".", "")
	try:
		return int(count_text)
	except ValueError:
		return None


def scroll_until_address_count_matches(page, city: str, expected_count: int, address_nodes) -> None:
	"""
	Slowly scroll with mouse wheel and keep checking address element count
	until it reaches expected market count.
	"""
	# Focus scroll area around result list to ensure wheel events apply to panel.
	try:
		address_nodes.first.hover()
	except Exception:
		pass

	last_count = -1
	stable_rounds = 0
	round_idx = 0

	while True:
		current_count = address_nodes.count()
		if current_count >= expected_count:
			print(f"城市 {city}: 地址元素数量已达到 {current_count}/{expected_count}，开始提取")
			return

		round_idx += 1
		if current_count == last_count:
			stable_rounds += 1
		else:
			stable_rounds = 0
			last_count = current_count

		if round_idx == 1 or round_idx % 5 == 0:
			print(
				f"城市 {city}: 已加载地址元素 {current_count}/{expected_count}，继续慢速滚动加载..."
			)

		if stable_rounds >= 10:
			print(
				f"城市 {city}: 地址数量长时间未增长（当前 {current_count}/{expected_count}）。"
				"如页面有额外验证或遮挡，请手动处理，脚本将继续等待并滚动。"
			)
			stable_rounds = 0

		# Scroll in small steps to avoid aggressive behavior.
		page.mouse.wheel(0, random.randint(500, 900))
		time.sleep(random.uniform(1.2, 2.4))


def extract_city_from_address(address: str) -> str | None:
	"""
	Extract city from patterns like:
	- Schönhauser Allee 80, 10439 Berlin
	- Daumstr. 90, 13599 Berlin / Haselhorst
	"""
	match = re.search(r",\s*\d{5}\s+(.+)$", address)
	if not match:
		return None

	city_part = normalize_spaces(match.group(1))
	city_only = city_part.split("/")[0].strip()
	return city_only


def get_city_match_key(city_name: str) -> str:
	"""Return the primary token used for matching, e.g. 'Mülheim an der Ruhr' -> 'Mülheim'."""
	normalized = normalize_spaces(city_name)
	if not normalized:
		return normalized
	return normalized.split(" ", 1)[0]


def normalize_address_city(address: str) -> str:
	"""
	Convert
	- "..., 13599 Berlin / Haselhorst"
	to
	- "..., 13599 Berlin"
	"""
	match = re.search(r"^(.*?,\s*\d{5}\s+)(.+)$", normalize_spaces(address))
	if not match:
		return normalize_spaces(address)

	prefix, city_part = match.groups()
	city_only = normalize_spaces(city_part).split("/")[0].strip()
	return f"{prefix}{city_only}"


def load_cities() -> list[str]:
	if not CITY_FILE.exists():
		raise FileNotFoundError(f"未找到城市文件: {CITY_FILE}")

	cities = [line.strip() for line in CITY_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
	if not cities:
		raise ValueError("city_name.txt 中没有可用城市")
	return cities


def normalize_record(record: str) -> str:
	return normalize_spaces(record)


def load_existing_record_set() -> set[str]:
	if not OUTPUT_FILE.exists():
		return set()

	records = set()
	for line in OUTPUT_FILE.read_text(encoding="utf-8").splitlines():
		normalized = normalize_record(line)
		if normalized:
			records.add(normalized)
	return records


def load_processed_cities() -> set[str]:
	if not PROGRESS_FILE.exists():
		return set()

	try:
		data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
	except json.JSONDecodeError:
		return set()

	processed = data.get("processed_cities", [])
	if not isinstance(processed, list):
		return set()

	result: set[str] = set()
	for item in processed:
		if isinstance(item, str):
			result.add(normalize_spaces(item))
	return result


def save_processed_cities(processed_cities: set[str]) -> None:
	payload = {
		"processed_cities": sorted(processed_cities),
		"updated_at": int(time.time()),
	}
	PROGRESS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_search_entry_locator(page):
	"""Return a robust locator for the market search entry in the dialog."""
	# The visible clickable element can be a div with aria-label, while the editable peer may be an input.
	return page.locator(
		'[aria-label="PLZ, Ort, Straße oder Marktname"], '
		'input[placeholder*="PLZ"], input[placeholder*="Ort"]'
	).first


def ensure_market_dialog_open(page) -> None:
	search_input = get_search_entry_locator(page)
	def search_input_visible() -> bool:
		return search_input.is_visible()

	wait_until(search_input_visible, "市场选择弹窗搜索框可见（请先手动点击 Markt wählen）")


def accept_cookie_if_present(page) -> None:
	cookie_buttons = [
		"Alle akzeptieren",
		"Akzeptieren",
		"Zustimmen",
	]
	for text in cookie_buttons:
		button = page.get_by_role("button", name=text).first
		if button.is_visible():
			button.click()
			random_pause(0.8, 1.6)
			return


def collect_city_matches_from_dialog(page, city: str) -> list[str]:
	city_target = get_city_match_key(city).casefold()

	# Use explicit result nodes from the market selector panel.
	result_summary = page.locator("span:has-text('Märkte gefunden')").first

	def result_summary_visible() -> bool:
		return result_summary.is_visible()

	wait_until(result_summary_visible, f"城市 {city} 的结果摘要可见")
	summary_text = normalize_spaces(result_summary.inner_text())
	expected_count = extract_market_count(summary_text)
	if expected_count is None:
		print(f"城市 {city}: 无法解析超市总数，摘要文本: {summary_text}")
		return []

	print(f"城市 {city}: 页面显示总数 {expected_count} 家，开始滚动加载全部地址元素")

	random_pause(0.5, 1.0)

	address_nodes = page.locator("address")

	def address_nodes_ready() -> bool:
		try:
			return address_nodes.count() > 0
		except Exception:
			return False

	wait_until(address_nodes_ready, f"城市 {city} 的地址列表可见")
	scroll_until_address_count_matches(page, city, expected_count, address_nodes)

	address_candidates: list[str] = []
	for i in range(address_nodes.count()):
		text = normalize_spaces(address_nodes.nth(i).inner_text())
		if re.search(r",\s*\d{5}\s+", text):
			address_candidates.append(text)

	filtered: list[str] = []
	seen = set()
	for address in address_candidates:
		city_from_address = extract_city_from_address(address)
		if not city_from_address:
			continue

		if get_city_match_key(city_from_address).casefold() == city_target:
			normalized_address = normalize_address_city(address)
			if normalized_address not in seen:
				seen.add(normalized_address)
				filtered.append(normalized_address)

	return filtered


def append_unique_records(records: list[str], existing_records: set[str]) -> int:
	if not records:
		return 0

	new_records: list[str] = []
	for record in records:
		normalized = normalize_record(record)
		if not normalized:
			continue
		if normalized in existing_records:
			continue
		existing_records.add(normalized)
		new_records.append(normalized)

	if not new_records:
		return 0

	with OUTPUT_FILE.open("a", encoding="utf-8") as f:
		for record in new_records:
			f.write(record + "\n")

	return len(new_records)


def open_page(p):
	cdp_url = "http://127.0.0.1:9222"
	browser = p.chromium.connect_over_cdp(cdp_url)
	if browser.contexts:
		context = browser.contexts[0]
	else:
		context = browser.new_context(locale="de-DE")

	page = context.new_page()
	print(f"已连接到现有浏览器: {cdp_url}")
	return browser, context, page


def main() -> None:
	cities = load_cities()
	existing_records = load_existing_record_set()
	processed_cities = load_processed_cities()

	with sync_playwright() as p:
		browser, context, page = open_page(p)

		page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
		random_pause(1.2, 2.4)
		accept_cookie_if_present(page)

		total_written = 0
		total_skipped_existing = 0

		for index, city in enumerate(cities, start=1):
			city_key = normalize_spaces(city)
			city_search_term = get_city_search_term(city)
			if city_key in processed_cities:
				print(f"[{index}/{len(cities)}] {city}: 已处理，跳过")
				continue

			ensure_market_dialog_open(page)

			search_input = get_search_entry_locator(page)

			def search_input_visible_for_city() -> bool:
				return search_input.is_visible()

			wait_until(search_input_visible_for_city, f"城市 {city} 的输入框可见")
			search_input.click()
			# Use keyboard-level editing after focusing entry; works for both div-based and input-based UI wrappers.
			page.keyboard.press("Control+a")
			page.keyboard.press("Backspace")
			random_pause(0.5, 1.0)

			# Type intentionally slower to reduce scraping pressure.
			page.keyboard.type(city_search_term, delay=random.randint(90, 160))
			random_pause(1.2, 2.2)

			records = collect_city_matches_from_dialog(page, city_search_term)
			written_count = append_unique_records(records, existing_records)
			skipped_count = len(records) - written_count
			total_written += written_count
			total_skipped_existing += max(skipped_count, 0)

			processed_cities.add(city_key)
			save_processed_cities(processed_cities)

			print(
				f"[{index}/{len(cities)}] {city} (搜索词: {city_search_term}): 匹配 {len(records)} 条, 新增 {written_count} 条, 已存在跳过 {max(skipped_count, 0)} 条"
			)

			# Extra gap between cities keeps the crawl pace conservative.
			random_pause(2.0, 4.0)

		print(
			f"抓取完成，新增写入 {total_written} 条，重复跳过 {total_skipped_existing} 条，输出文件: {OUTPUT_FILE}，进度文件: {PROGRESS_FILE}"
		)
		# Do not close user's existing browser session.
		page.close()


if __name__ == "__main__":
	main()
