from __future__ import annotations
from typing import List, Union, Annotated, Literal, Optional
from pydantic import BaseModel, Field, model_validator
import logging

# =========================
# Common base (no children)
# =========================
class _NodeCommon(BaseModel):
    level: str = Field(
        "construction_project",
        description=(
            "Hierarchy level: construction_project / individual_project / unit_project / "
            "sub_divisional_work / specialty_subdivision / sub_item_work."
        )
    )
    name: str = Field(
        "unnamed_work",
        description="Name of the work item. Example: 'Phase II Residential Tower #36'."
    )
    description: Optional[str] = Field("", description="Optional description.")


# =========================
# Parent node base
# =========================
class _ParentNodeBase(_NodeCommon):
    _level_cn: str = "(override)"
    _allowed_child: str = "(override)"

    children: List["WBSNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_children(self):
        for c in self.children:
            # Special handling for UnitProject that can have either sub_divisional_work or specialty_subdivision
            if self.level == "unit_project":
                if c.level not in ["sub_divisional_work", "specialty_subdivision"]:
                    raise ValueError(
                        f"{self._level_cn} must contain 'sub_divisional_work' or 'specialty_subdivision' nodes, "
                        f"but got '{c.level}'."
                    )
            else:
                if c.level != self._allowed_child:
                    raise ValueError(
                        f"{self._level_cn} must contain '{self._allowed_child}' nodes, "
                        f"but got '{c.level}'."
                    )
        return self


# =========================
# Leaf node base (no children)
# =========================
class _LeafNodeBase(_NodeCommon):
    _level_cn: str = "(override)"


# =========================
# Concrete hierarchy classes
# =========================
class ConstructionProject(_ParentNodeBase):
    level: Literal["construction_project"] = Field(
        "construction_project",
        description="Top-level project. Example: 滨江新区综合开发工程 / 城市更新一期工程."
    )
    _level_cn = "建设项目"
    _allowed_child = "individual_project"


class IndividualProject(_ParentNodeBase):
    level: Literal["individual_project"] = Field(
        "individual_project",
        description="Standalone component or section. Example: 住宅区一期 / 教学楼 A 栋."
    )
    _level_cn = "单项工程"
    _allowed_child = "unit_project"


class UnitProject(_ParentNodeBase):
    level: Literal["unit_project"] = Field(
        "unit_project",
        description="Professional unit. Example: 土建工程 / 电气工程 / 给排水工程."
    )
    _level_cn = "单位工程"
    _allowed_child = "sub_divisional_work"


class SubDivisionalWork(_ParentNodeBase):
    level: Literal["sub_divisional_work"] = Field(
        "sub_divisional_work",
        description="Division by system or structure. Example: 土石方工程 / 装饰装修工程."
    )
    _level_cn = "分部工程"
    _allowed_child = "specialty_subdivision"


class SpecialtySubdivision(_ParentNodeBase):
    level: Literal["specialty_subdivision"] = Field(
        "specialty_subdivision",
        description="Sub-division by craft/material. Example: 桩基工程 / 幕墙工程."
    )
    _level_cn = "子分部工程"
    _allowed_child = "sub_item_work"


class SubItemWork(_LeafNodeBase):
    level: Literal["sub_item_work"] = Field(
        "sub_item_work",
        description="Final measurable work item. Example: C30混凝土浇筑 / 钢筋绑扎."
    )
    _level_cn = "分项工程"

    unit: str = Field(
        "item",
        description="Measurement unit. Example: m3, m2, t, set."
    )
    quantity: float = Field(
        1.0,
        description="Quantity of the work item."
    )


# =========================
# Discriminated union
# =========================
WBSNode = Annotated[
    Union[
        ConstructionProject,
        IndividualProject,
        UnitProject,
        SubDivisionalWork,
        SpecialtySubdivision,
        SubItemWork,
    ],
    Field(discriminator="level"),
]


# =========================
# Root node
# =========================
class WBSRoot(ConstructionProject):
    """Root of the WBS tree (construction_project)."""
    pass
