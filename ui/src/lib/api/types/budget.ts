// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0


// Budget / Cost Control
export interface BudgetConfig {
	monthly_limit_usd: number | null;
	enabled: boolean;
	current_month_cost: number;
	current_month: string;
	by_model: Record<string, number>;
	tokens_by_model: Record<string, number>;
	by_feature: Record<string, number>;
	by_step: Record<string, number>;
	total_input_tokens: number;
	total_output_tokens: number;
	is_paused: boolean;
	paused_workflow_count: number;
}

export interface MonthlyCostEntry {
	year_month: string;
	total_cost_usd: number;
	by_model: Record<string, number>;
	total_input_tokens: number;
	total_output_tokens: number;
}

