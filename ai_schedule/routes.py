"""
AI Schedule Blueprint — Flask routes for the AI Scheduling module.

All endpoints use the /api/ai-schedule/ prefix and are registered
as a Flask Blueprint to maintain isolation from existing routes.
"""
import logging
import traceback
from dataclasses import asdict

from flask import Blueprint, jsonify, request

from ai_schedule.rule_analyzer import RuleAnalyzer
from ai_schedule.rule_validator import RuleValidator

ai_schedule_bp = Blueprint('ai_schedule', __name__, url_prefix='/api/ai-schedule')

NOT_IMPLEMENTED = {"ok": False, "error": "not_implemented"}


def _fetch_demands_from_bead_need(db, week_code: str) -> tuple[list[dict] | None, str | None]:
    """Helper: Fetch demands from schedule."BeadNeed" for a given week_code.

    Finds the closest date record to the target week's Monday,
    then builds demand entries from w1/w2/w3 columns.

    Returns:
        (demands_list, None) on success
        (None, error_message) on failure
    """
    import re as _re
    from datetime import date as date_type, timedelta
    from sqlalchemy import text

    match = _re.match(r'^(\d{4})-W(\d{1,2})$', week_code)
    if not match:
        return None, f"Invalid week_code format: '{week_code}'. Expected 'YYYY-WNN'."

    year = int(match.group(1))
    week_num = int(match.group(2))

    # Compute Monday of that ISO week
    try:
        jan4 = date_type(year, 1, 4)
        week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
        target_monday = week1_monday + timedelta(weeks=week_num - 1)
        target_monday_str = target_monday.isoformat()
    except (ValueError, OverflowError) as e:
        return None, f"Cannot compute date for week_code '{week_code}': {e}"

    try:
        # Find closest BeadNeed date
        result = db.session.execute(text("""
            SELECT date FROM (
                SELECT DISTINCT date FROM schedule."BeadNeed"
                WHERE date IS NOT NULL
            ) sub
            ORDER BY ABS(CAST(date AS date) - CAST(:target_date AS date)) ASC
            LIMIT 1
        """), {"target_date": target_monday_str})

        closest_row = result.fetchone()
        if not closest_row:
            return None, "No BeadNeed data found in database."

        source_date = str(closest_row[0])

        # Load rows for that date
        rows = db.session.execute(text("""
            SELECT pn, name, w1, w2, w3
            FROM schedule."BeadNeed"
            WHERE date = :d
            ORDER BY name
        """), {"d": source_date}).fetchall()

        if not rows:
            return None, f"No BeadNeed records found for date {source_date}."

        demands = []
        for row in rows:
            pn = str(row[0]).strip() if row[0] else ''
            name = str(row[1]).strip() if row[1] else ''
            w1 = float(row[2] or 0)
            w2 = float(row[3] or 0)
            w3 = float(row[4] or 0)

            if not name or not pn:
                continue

            if w1 > 0:
                demands.append({"marker": name, "pn": pn, "quantity": int(w1), "priority": 1})
            if w2 > 0:
                demands.append({"marker": name, "pn": pn, "quantity": int(w2), "priority": 2})
            if w3 > 0:
                demands.append({"marker": name, "pn": pn, "quantity": int(w3), "priority": 3})

        if not demands:
            return None, f"All w1/w2/w3 values are 0 for date {source_date}. No demand to schedule."

        return demands, None

    except Exception as e:
        return None, f"Database error when fetching BeadNeed: {str(e)}"


@ai_schedule_bp.route('/analyze-rules', methods=['POST'])
def analyze_rules():
    """Trigger historical schedule data rule analysis and validation.

    Steps:
    1. Instantiate RuleAnalyzer and run analyze_all() to extract rules from history
    2. Instantiate RuleValidator and run generate_validation_report() to validate
       derived rules against Base_Rule_Tables
    3. Return combined JSON with analysis_summary and validation_report

    Returns:
        200: JSON with ok=True, analysis_summary, validation_report
        500: JSON with ok=False, error details, and any partial results
    """
    from mrpFlask_5 import db

    analysis_summary = None
    validation_report = None

    try:
        # Step 1: Rule Analysis — extract patterns from historical data
        analyzer = RuleAnalyzer(db.session)
        summary = analyzer.analyze_all()
        analysis_summary = asdict(summary)

        # Step 2: Rule Validation — validate derived rules vs base rules
        validator = RuleValidator(db.session)
        report = validator.generate_validation_report()
        validation_report = asdict(report)

        return jsonify({
            "ok": True,
            "analysis_summary": analysis_summary,
            "validation_report": validation_report,
        }), 200

    except Exception as e:
        logging.error(f"[analyze-rules] Error during rule analysis: {e}")
        logging.error(traceback.format_exc())

        # Return partial results if any step completed before failure
        response = {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        if analysis_summary is not None:
            response["analysis_summary"] = analysis_summary
        if validation_report is not None:
            response["validation_report"] = validation_report

        return jsonify(response), 500


@ai_schedule_bp.route('/demands', methods=['GET'])
def get_demands():
    """Fetch demand data from BeadNeed table for a given week_code.

    Reads from schedule."BeadNeed", finds the date closest to the target week's
    Monday, and returns demands derived from w1, w2, w3 columns.

    BeadNeed columns used:
      - date: the date the record was saved for
      - pn: product number (料號)
      - name: marker name
      - w1, w2, w3: weekly need quantities
      - w1_batch, w2_batch, w3_batch: batch counts (informational)

    Priority mapping:
      - w1 → priority 1 (most urgent, must schedule)
      - w2 → priority 2
      - w3 → priority 3 (can be dropped if capacity insufficient)

    Query Parameters:
        week_code (str, required): Week identifier (e.g., '2026-W24')

    Returns:
        200: JSON with ok=True, demands array, source_date, week_code
        400: JSON with ok=False if week_code missing/invalid
        404: JSON with ok=False if no BeadNeed data found
        500: JSON with ok=False for server errors
    """
    from mrpFlask_5 import db
    from datetime import datetime as dt_type, timedelta

    week_code = request.args.get('week_code')
    if not week_code or not isinstance(week_code, str):
        return jsonify({
            "ok": False,
            "error": "Missing or invalid 'week_code' query parameter. Expected format: 'YYYY-WNN'.",
        }), 400

    # Parse week_code → year, week_num → Monday date of that week
    import re as _re
    match = _re.match(r'^(\d{4})-W(\d{1,2})$', week_code)
    if not match:
        return jsonify({
            "ok": False,
            "error": f"Invalid week_code format: '{week_code}'. Expected 'YYYY-WNN'.",
        }), 400

    year = int(match.group(1))
    week_num = int(match.group(2))

    # Compute Monday of that ISO week
    try:
        from datetime import date as date_type
        # ISO week: Monday of week 1 is the Monday of the week containing Jan 4
        jan4 = date_type(year, 1, 4)
        # Monday of ISO week 1
        week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
        target_monday = week1_monday + timedelta(weeks=week_num - 1)
        target_monday_str = target_monday.isoformat()
    except (ValueError, OverflowError) as e:
        return jsonify({
            "ok": False,
            "error": f"Cannot compute date for week_code '{week_code}': {e}",
        }), 400

    try:
        # Find the BeadNeed record date closest to target_monday
        # Strategy: get all distinct dates, pick the one closest to target_monday
        from sqlalchemy import text

        result = db.session.execute(text("""
            SELECT date FROM (
                SELECT DISTINCT date FROM schedule."BeadNeed"
                WHERE date IS NOT NULL
            ) sub
            ORDER BY ABS(CAST(date AS date) - CAST(:target_date AS date)) ASC
            LIMIT 1
        """), {"target_date": target_monday_str})

        closest_row = result.fetchone()
        if not closest_row:
            return jsonify({
                "ok": False,
                "error": f"No BeadNeed data found in database.",
            }), 404

        source_date = str(closest_row[0])

        # Load all BeadNeed rows for that date
        rows = db.session.execute(text("""
            SELECT pn, name, w1, w2, w3, w1_batch, w2_batch, w3_batch
            FROM schedule."BeadNeed"
            WHERE date = :d
            ORDER BY name
        """), {"d": source_date}).fetchall()

        if not rows:
            return jsonify({
                "ok": False,
                "error": f"No BeadNeed records found for date {source_date}.",
            }), 404

        # Build two views:
        # 1. "rows" — one row per marker/pn (for table display, matching BeadNeed layout)
        # 2. "demands" — split by priority for the scheduling engine
        rows_display = []
        demands = []
        for row in rows:
            pn = str(row[0]).strip() if row[0] else ''
            name = str(row[1]).strip() if row[1] else ''
            w1 = float(row[2] or 0)
            w2 = float(row[3] or 0)
            w3 = float(row[4] or 0)
            w1_batch = float(row[5] or 0)
            w2_batch = float(row[6] or 0)
            w3_batch = float(row[7] or 0)

            if not name or not pn:
                continue

            # One row per marker for display
            if w1 > 0 or w2 > 0 or w3 > 0:
                rows_display.append({
                    "marker": name,
                    "pn": pn,
                    "w1": int(w1) if w1 else 0,
                    "w2": int(w2) if w2 else 0,
                    "w3": int(w3) if w3 else 0,
                    "w1_batch": int(w1_batch) if w1_batch else 0,
                    "w2_batch": int(w2_batch) if w2_batch else 0,
                    "w3_batch": int(w3_batch) if w3_batch else 0,
                })

            # Split demands for scheduling engine
            if w1 > 0:
                demands.append({"marker": name, "pn": pn, "quantity": int(w1), "priority": 1})
            if w2 > 0:
                demands.append({"marker": name, "pn": pn, "quantity": int(w2), "priority": 2})
            if w3 > 0:
                demands.append({"marker": name, "pn": pn, "quantity": int(w3), "priority": 3})

        if not demands:
            return jsonify({
                "ok": False,
                "error": f"All w1/w2/w3 values are 0 for date {source_date}. No demand to schedule.",
            }), 404

        return jsonify({
            "ok": True,
            "week_code": week_code,
            "source_date": source_date,
            "target_monday": target_monday_str,
            "rows": rows_display,
            "demands": demands,
            "summary": {
                "total_markers": len(rows_display),
                "total_demands": len(demands),
                "w1_items": len([d for d in demands if d['priority'] == 1]),
                "w2_items": len([d for d in demands if d['priority'] == 2]),
                "w3_items": len([d for d in demands if d['priority'] == 3]),
                "total_quantity": sum(d['quantity'] for d in demands),
            },
        }), 200

    except Exception as e:
        logging.error(f"[demands] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/generate', methods=['POST'])
def generate():
    """Accept demand data and generate automatic schedule results.

    Supports two modes:
    1. Auto mode (demands_source="auto"): Reads demands from BeadNeed table
       based on week_code. Only week_code is required.
    2. Manual mode (default): Requires explicit demands array.

    Request JSON:
        {
            "week_code": "2026-W24",       (required)
            "demands_source": "auto",      (optional, default "manual")
            "demands": [                   (required when demands_source != "auto")
                {"marker": "...", "pn": "...", "quantity": 1300, "priority": 1}
            ],
            "resource_config": {           (optional)
                "holidays": ["六", "日"],
                "dryerMaintenance": [],
                "staffOffDays": {}
            }
        }

    Returns:
        200: JSON with ok=True, schedule_run_id, data, conflicts_summary, degradation_note
        400: JSON with ok=False if request validation fails
        404: JSON with ok=False if auto mode but no BeadNeed data found
        500: JSON with ok=False for server errors
    """
    from mrpFlask_5 import db
    from ai_schedule.scheduling_engine import SchedulingEngine

    # --- Request validation ---
    body = request.get_json(silent=True)
    if not body:
        return jsonify({
            "ok": False,
            "error": "Request body must be valid JSON.",
        }), 400

    week_code = body.get('week_code')
    if not week_code or not isinstance(week_code, str):
        return jsonify({
            "ok": False,
            "error": "Missing or invalid 'week_code' field. Expected format: 'YYYY-WNN'.",
        }), 400

    demands_source = body.get('demands_source', 'manual')

    if demands_source == 'auto':
        # --- Auto mode: fetch demands from BeadNeed ---
        demands, auto_error = _fetch_demands_from_bead_need(db, week_code)
        if auto_error:
            return jsonify({
                "ok": False,
                "error": auto_error,
            }), 404 if 'not found' in auto_error.lower() or 'no bead' in auto_error.lower() else 400
    else:
        # --- Manual mode: validate explicit demands array ---
        demands = body.get('demands')
        if not demands or not isinstance(demands, list) or len(demands) == 0:
            return jsonify({
                "ok": False,
                "error": "Missing or empty 'demands' array.",
            }), 400

        # Validate each demand entry has required fields
        for i, d in enumerate(demands):
            if not isinstance(d, dict):
                return jsonify({
                    "ok": False,
                    "error": f"demands[{i}] must be an object.",
                }), 400
            if not d.get('marker') or not d.get('pn') or d.get('quantity') is None:
                return jsonify({
                    "ok": False,
                    "error": (
                        f"demands[{i}] missing required fields. "
                        f"Each demand must have 'marker', 'pn', and 'quantity'."
                    ),
                }), 400
            if not isinstance(d['quantity'], (int, float)) or d['quantity'] <= 0:
                return jsonify({
                    "ok": False,
                    "error": f"demands[{i}].quantity must be a positive number.",
                }), 400

    resource_config = body.get('resource_config') or {}

    # --- Execute scheduling ---
    try:
        engine = SchedulingEngine(db.session)
        result = engine.generate(
            week_code=week_code,
            demands=demands,
            resource_config=resource_config,
        )

        return jsonify({
            "ok": True,
            "schedule_run_id": result["schedule_run_id"],
            "data": result["entries"],
            "conflicts_summary": result["conflicts_summary"],
            "degradation_note": result.get("degradation_note"),
        }), 200

    except ValueError as e:
        logging.warning(f"[generate] Validation error: {e}")
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": "ValueError",
        }), 400

    except RuntimeError as e:
        logging.error(f"[generate] Runtime error: {e}")
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": "RuntimeError",
        }), 500

    except Exception as e:
        logging.error(f"[generate] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/preview', methods=['GET'])
def preview():
    """Return generated schedule data for frontend preview with version filtering.

    Query Parameters:
        week_code (str, optional): Filter by week code (e.g., '2026-W24')
        schedule_run_id (str, optional): Filter by specific schedule run UUID
        status (str, optional): Filter by status (e.g., 'draft', 'approved', 'superseded')
        page (int, optional): Page number, default 1
        per_page (int, optional): Items per page, default 50
        sort_by (str, optional): Sort field — 'date' or 'priority', default 'date'
        sort_order (str, optional): Sort direction — 'asc' or 'desc', default 'asc'

    Returns:
        200: JSON with ok=True, data array, pagination info, and filters_applied
        500: JSON with ok=False for server errors
    """
    from mrpFlask_5 import db
    from ai_schedule.models import GeneratedSchedule

    try:
        # --- Parse query parameters ---
        week_code = request.args.get('week_code')
        schedule_run_id = request.args.get('schedule_run_id')
        status = request.args.get('status')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        sort_by = request.args.get('sort_by', 'date')
        sort_order = request.args.get('sort_order', 'asc')

        # Clamp pagination values
        page = max(1, page)
        per_page = max(1, min(per_page, 200))

        # --- Build query with filters ---
        query = GeneratedSchedule.query

        if week_code:
            query = query.filter(GeneratedSchedule.week_code == week_code)
        if schedule_run_id:
            query = query.filter(GeneratedSchedule.schedule_run_id == schedule_run_id)
        if status:
            query = query.filter(GeneratedSchedule.status == status)

        # --- Apply sorting ---
        if sort_by == 'priority':
            sort_column = GeneratedSchedule.priority
        else:
            sort_column = GeneratedSchedule.date

        if sort_order == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # --- Pagination ---
        total = query.count()
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        offset = (page - 1) * per_page
        entries = query.offset(offset).limit(per_page).all()

        # --- Serialize entries ---
        data = []
        for entry in entries:
            data.append({
                "id": entry.id,
                "schedule_run_id": str(entry.schedule_run_id) if entry.schedule_run_id else None,
                "week_code": entry.week_code,
                "date": entry.date.isoformat() if entry.date else None,
                "marker": entry.marker,
                "machine_port": entry.machine_port,
                "freeze_dryer": entry.freeze_dryer,
                "operator": entry.operator,
                "rd_time": entry.rd_time.isoformat() if entry.rd_time else None,
                "start_time": entry.start_time.isoformat() if entry.start_time else None,
                "end_time": entry.end_time.isoformat() if entry.end_time else None,
                "quantity": entry.quantity,
                "pn": entry.pn,
                "batch": entry.batch,
                "work_order": entry.work_order,
                "notes": entry.notes,
                "conflict_flag": entry.conflict_flag,
                "conflict_reason": entry.conflict_reason,
                "priority": entry.priority,
                "status": entry.status,
            })

        # --- Build filters_applied summary ---
        filters_applied = {}
        if week_code:
            filters_applied['week_code'] = week_code
        if schedule_run_id:
            filters_applied['schedule_run_id'] = schedule_run_id
        if status:
            filters_applied['status'] = status

        return jsonify({
            "ok": True,
            "data": data,
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": pages,
            },
            "filters_applied": filters_applied,
        }), 200

    except Exception as e:
        logging.error(f"[preview] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/update/<int:id>', methods=['PUT'])
def update(id):
    """Update a single schedule item and re-validate conflicts.

    Accepts field updates for a generated_schedule entry, applies changes,
    then re-runs ConflictDetector on all entries in the same schedule_run_id
    to detect cross-entry conflicts introduced by the update.

    Request JSON (all fields optional):
        {
            "date": "2026-06-09",
            "start_time": "14:30",
            "end_time": "18:00",
            "rd_time": "14:00",
            "machine_port": "P5",
            "freeze_dryer": "3",
            "operator": "張三",
            "notes": "備註",
            "priority": 1
        }

    Returns:
        200: JSON with ok=True, entry (updated entry), conflicts (for this entry)
        400: JSON with ok=False if request body is invalid
        404: JSON with ok=False if entry not found
        500: JSON with ok=False for server errors
    """
    from datetime import date as date_type, time as time_type, datetime as dt_type

    # --- Request validation (before heavy imports) ---
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({
            "ok": False,
            "error": "Request body must be valid JSON.",
        }), 400

    if not isinstance(body, dict) or len(body) == 0:
        return jsonify({
            "ok": False,
            "error": "Request body must be a non-empty JSON object.",
        }), 400

    # Define updateable fields and their expected types
    UPDATEABLE_FIELDS = {
        'date', 'start_time', 'end_time', 'rd_time',
        'machine_port', 'freeze_dryer', 'operator', 'notes', 'priority',
    }

    # Check for unknown fields
    unknown_fields = set(body.keys()) - UPDATEABLE_FIELDS
    if unknown_fields:
        return jsonify({
            "ok": False,
            "error": f"Unknown fields: {', '.join(sorted(unknown_fields))}. "
                     f"Updateable fields are: {', '.join(sorted(UPDATEABLE_FIELDS))}.",
        }), 400

    # --- Parse and validate field values ---
    def _parse_date_field(value):
        """Parse a date string (YYYY-MM-DD) into a date object."""
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                return dt_type.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid date format: '{value}'. Expected YYYY-MM-DD.")
        raise ValueError(f"Invalid date value type: {type(value).__name__}")

    def _parse_time_field(value, field_name):
        """Parse a time string (HH:MM or HH:MM:SS) into a time object."""
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            for fmt in ('%H:%M:%S', '%H:%M'):
                try:
                    return dt_type.strptime(value, fmt).time()
                except ValueError:
                    continue
            raise ValueError(
                f"Invalid time format for '{field_name}': '{value}'. "
                f"Expected HH:MM or HH:MM:SS."
            )
        raise ValueError(f"Invalid time value type for '{field_name}': {type(value).__name__}")

    parsed_updates = {}
    try:
        if 'date' in body:
            parsed_updates['date'] = _parse_date_field(body['date'])
        if 'start_time' in body:
            parsed_updates['start_time'] = _parse_time_field(body['start_time'], 'start_time')
        if 'end_time' in body:
            parsed_updates['end_time'] = _parse_time_field(body['end_time'], 'end_time')
        if 'rd_time' in body:
            parsed_updates['rd_time'] = _parse_time_field(body['rd_time'], 'rd_time')
        if 'machine_port' in body:
            val = body['machine_port']
            if val is not None and not isinstance(val, str):
                raise ValueError("machine_port must be a string or null.")
            parsed_updates['machine_port'] = val
        if 'freeze_dryer' in body:
            val = body['freeze_dryer']
            if val is not None and not isinstance(val, str):
                raise ValueError("freeze_dryer must be a string or null.")
            parsed_updates['freeze_dryer'] = val
        if 'operator' in body:
            val = body['operator']
            if val is not None and not isinstance(val, str):
                raise ValueError("operator must be a string or null.")
            parsed_updates['operator'] = val
        if 'notes' in body:
            val = body['notes']
            if val is not None and not isinstance(val, str):
                raise ValueError("notes must be a string or null.")
            parsed_updates['notes'] = val
        if 'priority' in body:
            val = body['priority']
            if val is not None and not isinstance(val, int):
                raise ValueError("priority must be an integer or null.")
            parsed_updates['priority'] = val
    except ValueError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 400

    # --- Heavy imports (deferred to avoid circular imports at module load) ---
    from mrpFlask_5 import db
    from ai_schedule.models import GeneratedSchedule
    from ai_schedule.conflict_detector import ConflictDetector
    from ai_schedule.scheduling_engine import SchedulingEngine

    try:
        # --- Load entry by id ---
        entry = GeneratedSchedule.query.get(id)
        if entry is None:
            return jsonify({
                "ok": False,
                "error": f"Schedule entry with id={id} not found.",
            }), 404

        # --- Apply updates ---
        for field, value in parsed_updates.items():
            setattr(entry, field, value)

        # --- Re-validate: load all entries in the same schedule_run_id ---
        run_entries = GeneratedSchedule.query.filter_by(
            schedule_run_id=entry.schedule_run_id
        ).all()

        # Convert ORM objects to dicts for ConflictDetector
        entry_dicts = []
        for e in run_entries:
            entry_dicts.append({
                'id': e.id,
                'date': e.date,
                'marker': e.marker,
                'machine_port': e.machine_port,
                'freeze_dryer': e.freeze_dryer,
                'operator': e.operator,
                'rd_time': e.rd_time,
                'start_time': e.start_time,
                'end_time': e.end_time,
                'quantity': e.quantity,
                'pn': e.pn,
                'batch': e.batch,
                'conflict_flag': e.conflict_flag,
                'conflict_reason': e.conflict_reason,
            })

        # --- Load rules for conflict detection ---
        engine = SchedulingEngine(db.session)
        rules = engine._load_rules()

        # --- Run conflict detection on all entries in the run ---
        detector = ConflictDetector(rules)
        all_conflicts = detector.detect_all(entry_dicts)

        # --- Update conflict_flag and conflict_reason for all entries in the run ---
        entry_orm_map = {e.id: e for e in run_entries}
        for entry_dict in entry_dicts:
            eid = entry_dict['id']
            orm_entry = entry_orm_map.get(eid)
            if orm_entry:
                orm_entry.conflict_flag = entry_dict.get('conflict_flag', False)
                orm_entry.conflict_reason = entry_dict.get('conflict_reason')

        # --- Commit all changes ---
        db.session.commit()

        # --- Build response: updated entry + conflicts for this entry ---
        # Collect conflicts for the updated entry
        entry_conflicts = [
            {
                "type": c.conflict_type,
                "description": c.description,
                "severity": c.severity,
            }
            for c in all_conflicts if c.entry_id == id
        ]

        # Serialize the updated entry
        entry_data = {
            "id": entry.id,
            "schedule_run_id": str(entry.schedule_run_id),
            "week_code": entry.week_code,
            "date": entry.date.isoformat() if entry.date else None,
            "marker": entry.marker,
            "machine_port": entry.machine_port,
            "freeze_dryer": entry.freeze_dryer,
            "operator": entry.operator,
            "rd_time": entry.rd_time.strftime('%H:%M') if entry.rd_time else None,
            "start_time": entry.start_time.strftime('%H:%M') if entry.start_time else None,
            "end_time": entry.end_time.strftime('%H:%M') if entry.end_time else None,
            "quantity": entry.quantity,
            "pn": entry.pn,
            "batch": entry.batch,
            "work_order": entry.work_order,
            "notes": entry.notes,
            "conflict_flag": entry.conflict_flag,
            "conflict_reason": entry.conflict_reason,
            "priority": entry.priority,
            "status": entry.status,
        }

        return jsonify({
            "ok": True,
            "entry": entry_data,
            "conflicts": entry_conflicts,
        }), 200

    except Exception as e:
        logging.error(f"[update] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/confirm', methods=['POST'])
def confirm():
    """Confirm and write approved schedule items to Official Schedule.

    Supports three modes:
    - "all": confirm all non-conflict entries (or all if force_confirm=true)
    - "selected": confirm only specified entry_ids
    - "rollback": mark the run as rolled back (no data deletion)

    Request JSON:
        {
            "schedule_run_id": "uuid-...",   (required)
            "mode": "all" | "selected" | "rollback",  (required)
            "entry_ids": [1, 2, 3],          (required when mode="selected")
            "force_confirm": false,          (optional, default false)
            "force_confirm_reason": "...",   (required when force_confirm=true)
            "confirmed_by": "admin"          (optional)
        }

    Returns:
        200: JSON with ok=True, confirmed_count, official_ids, audit_log_id
        400: JSON with ok=False for bad input
        404: JSON with ok=False if run not found
        409: JSON with ok=False for unresolved conflicts without force_confirm
        500: JSON with ok=False for server errors
    """
    import uuid as uuid_module
    from datetime import datetime as dt_type, timezone

    # --- Request validation ---
    body = request.get_json(silent=True)
    if not body:
        return jsonify({
            "ok": False,
            "error": "Request body must be valid JSON.",
        }), 400

    schedule_run_id_str = body.get('schedule_run_id')
    if not schedule_run_id_str or not isinstance(schedule_run_id_str, str):
        return jsonify({
            "ok": False,
            "error": "Missing or invalid 'schedule_run_id'. Must be a UUID string.",
        }), 400

    # Validate UUID format
    try:
        schedule_run_id = uuid_module.UUID(schedule_run_id_str)
    except (ValueError, AttributeError):
        return jsonify({
            "ok": False,
            "error": f"Invalid UUID format for 'schedule_run_id': '{schedule_run_id_str}'.",
        }), 400

    mode = body.get('mode')
    if mode not in ('all', 'selected', 'rollback'):
        return jsonify({
            "ok": False,
            "error": "Missing or invalid 'mode'. Must be 'all', 'selected', or 'rollback'.",
        }), 400

    entry_ids = body.get('entry_ids')
    if mode == 'selected':
        if not entry_ids or not isinstance(entry_ids, list) or len(entry_ids) == 0:
            return jsonify({
                "ok": False,
                "error": "'entry_ids' is required and must be a non-empty array when mode='selected'.",
            }), 400
        for i, eid in enumerate(entry_ids):
            if not isinstance(eid, int):
                return jsonify({
                    "ok": False,
                    "error": f"entry_ids[{i}] must be an integer.",
                }), 400

    force_confirm = body.get('force_confirm', False)
    if not isinstance(force_confirm, bool):
        return jsonify({
            "ok": False,
            "error": "'force_confirm' must be a boolean.",
        }), 400

    force_confirm_reason = body.get('force_confirm_reason')
    if force_confirm and (not force_confirm_reason or not isinstance(force_confirm_reason, str) or not force_confirm_reason.strip()):
        return jsonify({
            "ok": False,
            "error": "'force_confirm_reason' is required when force_confirm=true.",
        }), 400

    confirmed_by = body.get('confirmed_by')
    if confirmed_by is not None and not isinstance(confirmed_by, str):
        return jsonify({
            "ok": False,
            "error": "'confirmed_by' must be a string.",
        }), 400

    # --- Heavy imports ---
    from mrpFlask_5 import db
    from sqlalchemy import text
    from ai_schedule.models import GeneratedSchedule, AIScheduleAuditLog

    try:
        # --- Verify the schedule_run_id exists ---
        run_entries = GeneratedSchedule.query.filter_by(
            schedule_run_id=schedule_run_id
        ).all()

        if not run_entries:
            return jsonify({
                "ok": False,
                "error": f"Schedule run '{schedule_run_id_str}' not found.",
            }), 404

        # --- Handle rollback mode ---
        if mode == 'rollback':
            now = dt_type.now(timezone.utc)

            # Mark all entries in this run as 'rollback'
            for entry in run_entries:
                entry.status = 'rollback'
                entry.updated_at = now

            # Create audit log entry for rollback
            audit_log = AIScheduleAuditLog(
                schedule_run_id=schedule_run_id,
                action='rollback',
                confirmed_by=confirmed_by,
                rollback_at=now,
                rollback_by=confirmed_by,
                entries_count=len(run_entries),
                details={"schedule_run_id": str(schedule_run_id), "mode": "rollback"},
            )
            db.session.add(audit_log)
            db.session.commit()

            return jsonify({
                "ok": True,
                "confirmed_count": 0,
                "official_ids": [],
                "audit_log_id": audit_log.id,
                "rollback": True,
                "rollback_entries_count": len(run_entries),
            }), 200

        # --- Confirm flow (mode="all" or "selected") ---

        # Select entries to confirm
        if mode == 'all':
            if force_confirm:
                # Include all entries (even those with conflicts)
                entries_to_confirm = run_entries
            else:
                # Only include non-conflict entries
                entries_to_confirm = [e for e in run_entries if not e.conflict_flag]
        else:
            # mode == 'selected'
            entry_id_set = set(entry_ids)
            entries_to_confirm = [e for e in run_entries if e.id in entry_id_set]

            # Validate all requested IDs were found
            found_ids = {e.id for e in entries_to_confirm}
            missing_ids = entry_id_set - found_ids
            if missing_ids:
                return jsonify({
                    "ok": False,
                    "error": f"Entry IDs not found in this run: {sorted(missing_ids)}.",
                }), 400

        # Check for conflicts (when force_confirm is not set)
        if not force_confirm:
            conflict_entries = [e for e in entries_to_confirm if e.conflict_flag]
            if conflict_entries:
                conflict_ids = [e.id for e in conflict_entries]
                return jsonify({
                    "ok": False,
                    "error": "Cannot confirm entries with conflicts. Use force_confirm=true to override.",
                    "conflict_entry_ids": conflict_ids,
                    "conflict_count": len(conflict_ids),
                }), 409

        if not entries_to_confirm:
            return jsonify({
                "ok": False,
                "error": "No entries to confirm. All entries may have conflicts.",
            }), 400

        # --- Write each selected entry to DropletSchedule (official) ---
        official_ids = []
        now = dt_type.now(timezone.utc)

        for entry in entries_to_confirm:
            # Format date for DropletSchedule (uses string format 'YYYY/MM/DD')
            date_str = entry.date.strftime('%Y/%m/%d') if entry.date else None

            # Format time fields as HH:MM strings
            rd_time_str = entry.rd_time.strftime('%H:%M') if entry.rd_time else None
            start_time_str = entry.start_time.strftime('%H:%M') if entry.start_time else None
            end_time_str = entry.end_time.strftime('%H:%M') if entry.end_time else None

            # INSERT into DropletSchedule and get the new ID back
            insert_result = db.session.execute(
                text("""
                    INSERT INTO "P01_formualte_schedule"."DropletSchedule"
                    ("Pump", "Marker", "Lyophilizer", "Quantity", "Preparer",
                     "Date", "DrugGivenAt", "ExpectedTitrationStart",
                     "ExpectedTitrationEnd", "WorkOrder", "Lot", "Remark")
                    VALUES (:pump, :marker, :lyophilizer, :quantity, :preparer,
                            :date, :drug_given_at, :expected_start,
                            :expected_end, :work_order, :lot, :remark)
                    RETURNING id
                """),
                {
                    "pump": entry.machine_port,
                    "marker": entry.marker,
                    "lyophilizer": entry.freeze_dryer,
                    "quantity": entry.quantity,
                    "preparer": entry.operator,
                    "date": date_str,
                    "drug_given_at": rd_time_str,
                    "expected_start": start_time_str,
                    "expected_end": end_time_str,
                    "work_order": entry.work_order,
                    "lot": entry.batch,
                    "remark": entry.notes,
                }
            )
            new_official_id = insert_result.scalar()
            official_ids.append(new_official_id)

            # Update generated_schedule entry: record the official ID and mark approved
            entry.confirmed_official_id = new_official_id
            entry.status = 'approved'
            entry.updated_at = now

        # --- Mark other same-week runs as 'superseded' ---
        week_code = run_entries[0].week_code
        other_runs = GeneratedSchedule.query.filter(
            GeneratedSchedule.week_code == week_code,
            GeneratedSchedule.schedule_run_id != schedule_run_id,
            GeneratedSchedule.status.in_(['draft']),
        ).all()

        for other_entry in other_runs:
            other_entry.status = 'superseded'
            other_entry.updated_at = now

        # --- Create AIScheduleAuditLog entry ---
        audit_details = {
            "official_ids": official_ids,
            "schedule_run_id": str(schedule_run_id),
            "mode": mode,
        }
        if force_confirm:
            audit_details["force_confirm"] = True

        audit_action = 'force_confirm' if force_confirm else 'confirm'

        audit_log = AIScheduleAuditLog(
            schedule_run_id=schedule_run_id,
            action=audit_action,
            confirmed_by=confirmed_by,
            entries_count=len(entries_to_confirm),
            force_confirm_reason=force_confirm_reason if force_confirm else None,
            details=audit_details,
        )
        db.session.add(audit_log)

        # --- Commit all changes ---
        db.session.commit()

        # --- Excel sync (decoupled from RDS transaction) ---
        # Call ExcelSyncService after successful RDS commit.
        # If Excel sync fails, we log the error but do NOT rollback the RDS commit.
        sync_status = "not_attempted"
        sync_error = None
        try:
            from ai_schedule.excel_sync_service import ExcelSyncService, SyncResult

            # Extract week number from week_code (e.g., "2026-W24" -> 24)
            week_num = None
            if week_code and '-W' in week_code:
                try:
                    week_num = int(week_code.split('-W')[1])
                except (IndexError, ValueError):
                    pass

            if week_num is not None:
                # Build entry dicts for Excel sync
                excel_entries = []
                for entry in entries_to_confirm:
                    excel_entries.append({
                        "date": entry.date,
                        "marker": entry.marker,
                        "machine_port": entry.machine_port,
                        "freeze_dryer": entry.freeze_dryer,
                        "operator": entry.operator,
                        "rd_time": entry.rd_time,
                        "start_time": entry.start_time,
                        "end_time": entry.end_time,
                        "quantity": entry.quantity,
                        "pn": entry.pn,
                        "batch": entry.batch,
                        "work_order": entry.work_order,
                        "notes": entry.notes,
                        "formula": "",
                    })

                service = ExcelSyncService()
                result = service.sync_to_excel(excel_entries, week_num)
                sync_status = result.status
                sync_error = result.error

                if result.status == "failed":
                    logging.error(
                        f"[confirm] Excel sync failed (RDS commit preserved): "
                        f"{result.error}"
                    )
            else:
                sync_status = "skipped"
                sync_error = f"Could not parse week number from week_code: {week_code}"
                logging.warning(f"[confirm] {sync_error}")

        except Exception as excel_exc:
            sync_status = "failed"
            sync_error = str(excel_exc)
            logging.error(
                f"[confirm] Excel sync exception (RDS commit preserved): {excel_exc}"
            )

        return jsonify({
            "ok": True,
            "confirmed_count": len(official_ids),
            "official_ids": official_ids,
            "audit_log_id": audit_log.id,
            "sync_status": sync_status,
            "sync_error": sync_error,
        }), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"[confirm] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/validate', methods=['POST'])
def validate():
    """Run constraint validation on specified schedule items and return conflicts.

    Accepts a list of entry IDs, loads corresponding generated_schedule entries,
    runs ConflictDetector with scheduling rules, updates entries in the database
    with conflict results, and returns per-entry validation results.

    Request JSON:
        {
            "entry_ids": [1, 2, 3]
        }

    Returns:
        200: JSON with ok=True, results array, and summary
        400: JSON with ok=False if entry_ids missing or invalid
        500: JSON with ok=False for server errors
    """
    # --- Request validation (before heavy imports) ---
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({
            "ok": False,
            "error": "Request body must be valid JSON.",
        }), 400

    entry_ids = body.get('entry_ids')
    if not entry_ids or not isinstance(entry_ids, list) or len(entry_ids) == 0:
        return jsonify({
            "ok": False,
            "error": "Missing or empty 'entry_ids' array.",
        }), 400

    # Validate that all entry_ids are integers
    for i, eid in enumerate(entry_ids):
        if not isinstance(eid, int):
            return jsonify({
                "ok": False,
                "error": f"entry_ids[{i}] must be an integer.",
            }), 400

    # --- Heavy imports (deferred to avoid circular imports at module load) ---
    from mrpFlask_5 import db
    from ai_schedule.models import GeneratedSchedule
    from ai_schedule.conflict_detector import ConflictDetector
    from ai_schedule.scheduling_engine import SchedulingEngine

    try:
        # --- Load entries from generated_schedule ---
        entries = GeneratedSchedule.query.filter(
            GeneratedSchedule.id.in_(entry_ids)
        ).all()

        # Convert ORM objects to dicts for ConflictDetector
        entry_dicts = []
        for entry in entries:
            entry_dicts.append({
                'id': entry.id,
                'date': entry.date,
                'marker': entry.marker,
                'machine_port': entry.machine_port,
                'freeze_dryer': entry.freeze_dryer,
                'operator': entry.operator,
                'rd_time': entry.rd_time,
                'start_time': entry.start_time,
                'end_time': entry.end_time,
                'quantity': entry.quantity,
                'pn': entry.pn,
                'batch': entry.batch,
                'conflict_flag': entry.conflict_flag,
                'conflict_reason': entry.conflict_reason,
            })

        # --- Load rules ---
        engine = SchedulingEngine(db.session)
        rules = engine._load_rules()

        # --- Run conflict detection ---
        detector = ConflictDetector(rules)
        conflicts = detector.detect_all(entry_dicts)

        # --- Update entries in the database with conflict results ---
        entry_orm_map = {entry.id: entry for entry in entries}
        for entry_dict in entry_dicts:
            eid = entry_dict['id']
            orm_entry = entry_orm_map.get(eid)
            if orm_entry:
                orm_entry.conflict_flag = entry_dict.get('conflict_flag', False)
                orm_entry.conflict_reason = entry_dict.get('conflict_reason')

        db.session.commit()

        # --- Build per-entry results ---
        # Group conflicts by entry_id
        conflicts_by_entry: dict[int, list[dict]] = {}
        for conflict in conflicts:
            eid = conflict.entry_id
            if eid not in conflicts_by_entry:
                conflicts_by_entry[eid] = []
            conflicts_by_entry[eid].append({
                "type": conflict.conflict_type,
                "description": conflict.description,
                "severity": conflict.severity,
            })

        results = []
        valid_count = 0
        conflict_count = 0
        for eid in entry_ids:
            entry_conflicts = conflicts_by_entry.get(eid, [])
            is_valid = len(entry_conflicts) == 0
            if is_valid:
                valid_count += 1
            else:
                conflict_count += 1
            results.append({
                "id": eid,
                "valid": is_valid,
                "conflicts": entry_conflicts,
            })

        return jsonify({
            "ok": True,
            "results": results,
            "summary": {
                "total_entries": len(entry_ids),
                "valid_count": valid_count,
                "conflict_count": conflict_count,
            },
        }), 200

    except Exception as e:
        logging.error(f"[validate] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/suggestions/<int:id>', methods=['GET'])
def suggestions(id):
    """Return AI adjustment suggestions for a specific conflicting schedule item.

    Calls AIAdvisor.get_suggestions() to generate alternative scheduling
    suggestions (machine swap, time shift, operator change) for an entry
    that has conflicts.

    Returns:
        200: JSON with ok=True, entry_id, suggestions array
        404: JSON with ok=False if entry not found
        500: JSON with ok=False for server errors
    """
    from mrpFlask_5 import db
    from ai_schedule.models import GeneratedSchedule
    from ai_schedule.ai_advisor import AIAdvisor

    try:
        # Check entry existence for proper 404
        entry = GeneratedSchedule.query.get(id)
        if entry is None:
            return jsonify({
                "ok": False,
                "error": f"Schedule entry with id={id} not found.",
            }), 404

        # Generate suggestions via AIAdvisor
        advisor = AIAdvisor(db.session)
        suggestions_list = advisor.get_suggestions(id)

        return jsonify({
            "ok": True,
            "entry_id": id,
            "suggestions": suggestions_list,
        }), 200

    except Exception as e:
        logging.error(f"[suggestions] Unexpected error for entry {id}: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500


@ai_schedule_bp.route('/validation-report', methods=['GET'])
def validation_report():
    """Return the latest derived-rule vs base-rule consistency validation report.

    Calls RuleValidator.generate_validation_report() to validate derived rules
    against Base_Rule_Tables and return the consistency report.

    Returns:
        200: JSON with ok=True, report dict (passed, conflicts_found, auto_corrected, conflict_details)
        500: JSON with ok=False for server errors
    """
    from mrpFlask_5 import db
    from ai_schedule.rule_validator import RuleValidator

    try:
        validator = RuleValidator(db.session)
        report = validator.generate_validation_report()

        return jsonify({
            "ok": True,
            "report": asdict(report),
        }), 200

    except Exception as e:
        logging.error(f"[validation-report] Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }), 500
