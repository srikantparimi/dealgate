"""The six engagement templates in build-guide §7.

Each template is a pure class:

* ``required_inputs()`` — declared input field names.
* ``validate(inputs)`` — returns the list of missing/incomplete fields.
* ``compute(inputs)`` — returns a :class:`TemplateResult`. Missing cost
  yields ``complete=False``; it never raises. Actually invalid data
  (negative revenue, unknown location) still raises.
"""

from app.gm.templates.assessment import AssessmentTemplate
from app.gm.templates.fixed_price import FixedPriceTemplate
from app.gm.templates.managed_service import ManagedServiceTemplate
from app.gm.templates.single_resource import SingleResourceTemplate
from app.gm.templates.staff_aug import StaffAugTemplate
from app.gm.templates.tm import TMTemplate

__all__ = [
    "AssessmentTemplate",
    "FixedPriceTemplate",
    "ManagedServiceTemplate",
    "SingleResourceTemplate",
    "StaffAugTemplate",
    "TMTemplate",
]
