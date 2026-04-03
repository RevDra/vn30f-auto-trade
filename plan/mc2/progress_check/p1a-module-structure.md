# p1a-module-structure — Tách module structure replay-engine

- **Status**: ✅ done
- **Depends on**: (none — root task)
- **Blocks**: p1b, p1c, p1d, p1e, p1f, p1g, p3a

## Description
Refactor main.py 305 dòng thành: engine.py, risk.py, fees.py, metrics.py, session.py, persistence.py, listeners.py, schemas.py, config.py, constants.py

## Acceptance Criteria
- [ ] `services/replay-engine/app/` package tạo đúng structure
- [ ] Tất cả existing tests pass sau refactor
- [ ] Không thay đổi behavior — chỉ tách file
- [ ] imports giữa modules đúng, không circular

## Progress Log
<!-- Ghi log mỗi session work: date, what done, result -->

## Error Log
<!-- Ghi errors gặp phải: date, error, root cause, fix -->

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
