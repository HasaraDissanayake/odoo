/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

// ── Colour palette ────────────────────────────────────────────
const COLORS = {
    blue:   { bg: "rgba(59,  130, 246, 0.75)", border: "rgba(59,  130, 246, 1)" },
    green:  { bg: "rgba(16,  185, 129, 0.75)", border: "rgba(16,  185, 129, 1)" },
    red:    { bg: "rgba(239, 68,  68,  0.75)", border: "rgba(239, 68,  68,  1)" },
    purple: { bg: "rgba(139, 92,  246, 0.75)", border: "rgba(139, 92,  246, 1)" },
    orange: { bg: "rgba(245, 158, 11,  0.75)", border: "rgba(245, 158, 11,  1)" },
};

const MULTI_COLORS = [
    COLORS.blue.bg, COLORS.green.bg, COLORS.purple.bg, COLORS.red.bg, COLORS.orange.bg,
];

const BUCKET_COLORS = [
    COLORS.red.bg, COLORS.orange.bg, COLORS.green.bg, COLORS.blue.bg,
];

const BASE_OPTIONS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
};

export class LmsDashboard extends Component {
    static template = "lms_student.LmsDashboard";

    setup() {
        this.orm    = useService("orm");
        this.action = useService("action");

        this.state = useState({
            isTeacher:   false,
            loaded:      false,
            noProfile:   false,
            studentName: "",
            kpis:        {},
            atRisk:      [],
        });

        /** Resolved Chart constructor (loaded dynamically). */
        this._Chart     = null;
        this._charts    = {};
        this._chartData = {};

        useEffect(
            (loaded) => {
                if (loaded) {
                    this._renderCharts();
                }
            },
            () => [this.state.loaded],
        );

        onMounted(() => { this._loadData(); });

        onWillUnmount(() => {
            Object.values(this._charts).forEach((c) => c.destroy());
        });
    }

    // ── Data + Chart.js loading ───────────────────────────────────

    async _loadData() {
        // Role detection is done server-side in get_dashboard_data() to avoid
        // issues with Odoo 19's privilege_id group model where implied-group
        // membership (Manager → Teacher → Student) may not propagate correctly
        // when has_group() is called from the browser.
        const data = await this.orm.call("lms.dashboard", "get_dashboard_data", []);

        if (data.role === "teacher") {
            this.state.isTeacher = true;
            this.state.kpis   = data.kpis;
            this.state.atRisk = data.at_risk;
            this._chartData   = data.charts;
        } else if (data.role === "no_profile") {
            this.state.noProfile = true;
        } else {
            // role === "student"
            this.state.studentName = data.student_name;
            this.state.kpis        = data.kpis;
            this._chartData        = data.charts;
        }

        // Load Chart.js dynamically so a missing module never prevents
        // this component from registering in the actions registry.
        await this._initChartJs();
        this.state.loaded = true;
    }

    /**
     * Load Chart.js via Odoo's built-in chartjs_lib bundle, which registers
     * Chart globally on window. Falls back to window.Chart if already present.
     */
    async _initChartJs() {
        if (this._Chart) return;

        // Primary: use Odoo's bundled chartjs_lib (same as graph view / survey)
        try {
            await loadBundle("web.chartjs_lib");
            if (typeof window !== "undefined" && window.Chart) {
                this._Chart = window.Chart;
                return;
            }
        } catch (_) { /* fall through */ }

        // Fallback: chart.js may already be on window from another bundle
        if (typeof window !== "undefined" && window.Chart) {
            this._Chart = window.Chart;
            return;
        }

        console.warn("[LMS Dashboard] chart.js could not be loaded. Charts will not render.");
    }

    // ── Chart rendering ───────────────────────────────────────────

    _renderCharts() {
        if (!this._Chart) return;
        if (this.state.isTeacher) {
            this._renderTeacherCharts();
        } else if (!this.state.noProfile) {
            this._renderStudentCharts();
        }
    }

    _renderTeacherCharts() {
        const cd = this._chartData;

        this._makeChart("lms-chart-enrollments", "bar", {
            labels:   cd.enrollments_by_course.labels,
            datasets: [{
                label: "Enrollments",
                data:  cd.enrollments_by_course.values,
                backgroundColor: COLORS.blue.bg,
                borderColor:     COLORS.blue.border,
                borderWidth: 1,
            }],
        });

        this._makeChart("lms-chart-status", "doughnut", {
            labels:   cd.student_status.labels,
            datasets: [{
                data:            cd.student_status.values,
                backgroundColor: MULTI_COLORS,
                borderWidth: 2,
            }],
        }, { plugins: { legend: { display: true, position: "bottom" } } });

        this._makeChart("lms-chart-attendance", "bar", {
            labels:   cd.attendance_by_course.labels,
            datasets: [{
                label: "Avg Attendance %",
                data:  cd.attendance_by_course.values,
                backgroundColor: COLORS.green.bg,
                borderColor:     COLORS.green.border,
                borderWidth: 1,
            }],
        }, { scales: { y: { min: 0, max: 100 } } });

        this._makeChart("lms-chart-grades", "bar", {
            labels:   cd.grade_distribution.labels,
            datasets: [{
                label: "Students",
                data:  cd.grade_distribution.values,
                backgroundColor: BUCKET_COLORS,
                borderWidth: 1,
            }],
        });

        this._makeChart("lms-chart-trend", "line", {
            labels:   cd.score_trend.labels,
            datasets: [{
                label:           "Avg Score",
                data:            cd.score_trend.values,
                borderColor:     COLORS.purple.border,
                backgroundColor: COLORS.purple.bg,
                tension: 0.35,
                fill: true,
                pointRadius: 4,
            }],
        }, { plugins: { legend: { display: true } } });
    }

    _renderStudentCharts() {
        const cd = this._chartData;

        this._makeChart("lms-chart-my-grades", "bar", {
            labels:   cd.grades_by_course.labels,
            datasets: [{
                label: "Avg Grade %",
                data:  cd.grades_by_course.values,
                backgroundColor: COLORS.blue.bg,
                borderColor:     COLORS.blue.border,
                borderWidth: 1,
            }],
        }, { scales: { y: { min: 0, max: 100 } } });

        this._makeChart("lms-chart-my-attendance", "bar", {
            labels:   cd.attendance_by_course.labels,
            datasets: [{
                label: "Attendance %",
                data:  cd.attendance_by_course.values,
                backgroundColor: COLORS.green.bg,
                borderColor:     COLORS.green.border,
                borderWidth: 1,
            }],
        }, { scales: { y: { min: 0, max: 100 } } });

        this._makeChart("lms-chart-gpa", "line", {
            labels:   cd.gpa_by_semester.labels,
            datasets: [{
                label:           "GPA",
                data:            cd.gpa_by_semester.values,
                borderColor:     COLORS.purple.border,
                backgroundColor: COLORS.purple.bg,
                tension: 0.35,
                fill: true,
                pointRadius: 5,
            }],
        }, {
            scales: { y: { min: 0, max: 4 } },
            plugins: { legend: { display: true } },
        });
    }

    _makeChart(canvasId, type, data, extraOptions = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !this._Chart) return;

        if (this._charts[canvasId]) {
            this._charts[canvasId].destroy();
        }

        const options = { ...BASE_OPTIONS, ...extraOptions };
        if (extraOptions.plugins) {
            options.plugins = { ...BASE_OPTIONS.plugins, ...extraOptions.plugins };
        }

        this._charts[canvasId] = new this._Chart(canvas, { type, data, options });
    }

    // ── Navigation ────────────────────────────────────────────────

    openStudent(studentId) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            res_model: "lms.student",
            res_id:    studentId,
            views:     [[false, "form"]],
            target:    "current",
        });
    }
}

registry.category("actions").add("lms_dashboard", LmsDashboard);
