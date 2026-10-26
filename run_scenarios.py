"""Автоматический прогон тестовых диалогов через API с автооценкой и отчётом.

Примеры запуска:
  python run_scenarios.py                         # все сценарии по 1 разу
  python run_scenarios.py --critical --repeat 3   # критичные сценарии по 3 раза
  python run_scenarios.py --repeat 3              # все сценарии по 3 раза
  python run_scenarios.py --assistant hr          # только HR-ассистент
  python run_scenarios.py --scenario sales_discount_pressure
  python run_scenarios.py --nocode                # версии промптов для GPTs и no-code

Каждый прогон оценивается автоматически по ожиданиям из tests/scenarios.json (поле "expect").
Отчёт: reports/scenarios_<дата>.md, заявки: reports/handoffs_<дата>.jsonl.
Код выхода 1, если хотя бы один прогон не прошёл автооценку.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.assistants import ASSISTANTS
from app.chat import AssistantError, ChatSession, Reply, create_client
from app.evaluate import evaluate
from app.handoff import save_handoff
from config import REPORTS_DIR, SCENARIOS_FILE, get_settings


def load_scenarios(path: Path) -> List[Dict[str, Any]]:
    scenarios = json.loads(path.read_text(encoding="utf-8"))
    for sc in scenarios:
        if sc.get("assistant") not in ASSISTANTS:
            raise ValueError(f"Сценарий {sc.get('id')!r}: неизвестный ассистент {sc.get('assistant')!r}")
        if "expect" not in sc:
            raise ValueError(f"Сценарий {sc.get('id')!r}: нет поля expect с ожидаемым поведением")
    return scenarios


def run_one(client, settings, sc: Dict[str, Any], variant: str, handoffs_path: Path) -> Tuple[List[str], List[str]]:
    """Прогоняет один диалог. Возвращает строки отчёта и список причин провала."""
    session = ChatSession(
        client, sc["assistant"], model=settings.model,
        temperature=settings.temperature, max_history_messages=settings.max_history_messages,
        variant=variant,
    )
    lines: List[str] = []
    replies: List[str] = []
    handoffs: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def add(reply: Reply) -> None:
        lines.append(f"**Ассистент:** {reply.text}\n")
        replies.append(reply.text)
        for data in reply.handoffs:
            record = save_handoff(data, source=session.key, path=handoffs_path)
            handoffs.append(record)
            lines.append(
                f"> Заявка {record['id']} → `{record['to']}` | тип: `{record['type']}` | "
                f"приоритет: `{record['priority']}` | {record['summary']}\n"
            )
        for error in reply.errors:
            warnings.append(error)
            lines.append(f"> ВНИМАНИЕ: {error}\n")

    add(session.start())
    for message in sc["messages"]:
        lines.append(f"**Пользователь:** {message}\n")
        add(session.ask(message))
    return lines, evaluate(sc["expect"], replies, handoffs, warnings, variant)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Прогон тестовых сценариев с автооценкой")
    parser.add_argument("--assistant", choices=list(ASSISTANTS), help="только этот ассистент")
    parser.add_argument("--scenario", help="только сценарий с этим id")
    parser.add_argument("--critical", action="store_true", help="только критичные сценарии")
    parser.add_argument("--repeat", type=int, default=1, help="сколько раз прогонять каждый сценарий")
    parser.add_argument("--nocode", action="store_true", help="проверить промпты из prompts_nocode/")
    args = parser.parse_args()
    if args.repeat < 1:
        print("[ОШИБКА] --repeat должен быть не меньше 1")
        return 1

    try:
        settings = get_settings()
    except RuntimeError as exc:
        print(f"[ОШИБКА] {exc}")
        return 1

    scenarios = load_scenarios(SCENARIOS_FILE)
    if args.assistant:
        scenarios = [s for s in scenarios if s["assistant"] == args.assistant]
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
    if args.critical:
        scenarios = [s for s in scenarios if s.get("critical")]
    if not scenarios:
        print("Нет сценариев под заданный фильтр.")
        return 1

    client = create_client(settings)
    variant = "nocode" if args.nocode else "full"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M") + ("_nocode" if args.nocode else "")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"scenarios_{stamp}.md"
    handoffs_path = REPORTS_DIR / f"handoffs_{stamp}.jsonl"

    body: List[str] = []
    results: Dict[str, List[bool]] = {}
    stop = False
    for sc in scenarios:
        results[sc["id"]] = []
        mark = " · критичный" if sc.get("critical") else ""
        body += [f"\n## {sc['id']} — {sc['title']}{mark}\n",
                 f"*Что проверяем:* {sc['check']}\n"]
        for run in range(1, args.repeat + 1):
            label = f" (прогон {run}/{args.repeat})" if args.repeat > 1 else ""
            print(f"→ {sc['id']}{label}", end=" ", flush=True)
            if args.repeat > 1:
                body.append(f"\n### Прогон {run}\n")
            try:
                lines, problems = run_one(client, settings, sc, variant, handoffs_path)
            except AssistantError as exc:
                body.append(f"> ОШИБКА API: {exc}\n")
                print(f"\n   [ОШИБКА] {exc}")
                results[sc["id"]].append(False)
                if "Ключ API" in str(exc) or "не найдена" in str(exc):
                    stop = True  # дальше запускать бессмысленно
                    break
                continue
            body += lines
            ok = not problems
            results[sc["id"]].append(ok)
            print("ОК" if ok else "ПРОВАЛ")
            if ok:
                body.append("**Автооценка:** ✅ пройден\n")
            else:
                body.append("**Автооценка:** ❌ не пройден\n" + "".join(f"- {p}\n" for p in problems))
        if stop:
            break

    total_runs = sum(len(v) for v in results.values())
    passed_runs = sum(sum(v) for v in results.values())
    header = [
        f"# Прогон тестовых сценариев — {datetime.now():%d.%m.%Y %H:%M}\n",
        f"Модель: `{settings.model}`, temperature: {settings.temperature}, промпты: `{variant}`, "
        f"повторов: {args.repeat}\n",
        f"**Итог: {passed_runs} из {total_runs} прогонов пройдены.**\n",
        "| Сценарий | Критичный | Пройдено |", "| --- | --- | --- |",
    ]
    by_id = {s["id"]: s for s in scenarios}
    for sid, res in results.items():
        header.append(f"| {sid} | {'да' if by_id[sid].get('critical') else ''} | {sum(res)} из {len(res)} |")
    report_path.write_text("\n".join(header) + "\n" + "\n".join(body), encoding="utf-8")

    print(f"\nИтог: {passed_runs} из {total_runs} прогонов пройдены")
    for sid, res in results.items():
        print(f"  {sid}: {sum(res)}/{len(res)}")
    print(f"Отчёт: {report_path}")
    return 0 if passed_runs == total_runs else 1


if __name__ == "__main__":
    sys.exit(main())
