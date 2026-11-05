# Общее оформление графиков: цвета групп, белый фон, сохранение в images/.

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from src.config import ROOT

IMAGES_DIR = ROOT / "images"

# одинаковые цвета для групп во всех графиках
GROUP_COLORS = {"control": "#2a78d6", "treatment": "#eb6834"}
# цвета моделей не пересекаются с цветами групп
MODEL_COLORS = {"response": "#8c6bb1", "t_learner": "#1b9e77", "class_transformation": "#c49a00", "inverse_response": "#d6604d"}
MODEL_NAMES = {
    "response": "модель отклика",
    "t_learner": "T-learner",
    "class_transformation": "трансформация классов",
    "inverse_response": "обратный отклик",
}
INK = "#52514e"
GRID = "#e4e3df"


def setup() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.titlesize": 11,
        "axes.titlelocation": "left",
        "legend.frameon": False,
    })


def save(fig, name: str) -> None:
    IMAGES_DIR.mkdir(exist_ok=True)
    fig.savefig(IMAGES_DIR / name, dpi=150, facecolor="white", bbox_inches="tight")


def decimal_comma(axis) -> None:
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−")))


def thousands(axis) -> None:
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " ")))
