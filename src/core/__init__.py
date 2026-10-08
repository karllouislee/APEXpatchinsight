"""Domain layer: models and pure computations.

Nothing here touches Streamlit, the network, or the process environment
(``core.settings`` is the deliberate exception — it reads ``.env`` once).
That keeps the rules testable without a running app.
"""
