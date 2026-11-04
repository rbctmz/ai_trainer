"""Fallback display of the same shared backup status and retry operation."""
import streamlit as st
from services.snapshot_runtime import backup_status, get_runtime


def _render(database) -> None:
    runner = get_runtime(database)
    runner.start()
    status = backup_status(database)
    if status['state'] == 'disabled':
        st.caption('Автоматические резервные копии выключены.')
        return
    if status['state'] == 'degraded':
        st.warning('Данные сохранены, резервная копия не обновлена.')
    elif status['state'] == 'unknown':
        st.warning('Состояние резервной копии неизвестно.')
    else:
        st.caption('Резервная копия проверена.')
    timestamp = status['last_snapshot_at']
    st.caption(f'Последняя проверенная копия: {timestamp}' if timestamp else 'Время последней проверенной копии неизвестно.')
    if status['state'] != 'ready' and st.button('Повторить проверку резервной копии', key='retry_backup_check'):
        runner.check('manual_retry')
        st.rerun()


# Retain the declared Streamlit>=1.28 fallback; modern runtimes refresh this
# small display every minute, without rerunning provider/business commands.
_fragment = getattr(st, 'fragment', None)
render_backup_status = _fragment(run_every=60)(_render) if callable(_fragment) else _render
