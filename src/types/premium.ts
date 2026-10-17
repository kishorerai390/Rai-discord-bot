export interface PricingPlan {
  id: string;
  name: string;
  amount: number; // in currency units (e.g. 4.99 or 499 INR)
  interval: "monthly" | "yearly" | "lifetime";
  currency: string;
  description: string;
  features: string[];
  popular?: boolean;
}

export interface UserEntitlement {
  user_id: string;
  is_premium: boolean;
  plan: string;
  status: "active" | "inactive" | "cancelled" | "past_due";
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  provider: string;
  perks: {
    boosted_volume: boolean;
    twenty_four_seven: boolean;
    studio_dsp: boolean;
    unlimited_queue: boolean;
    priority_precaching: boolean;
    custom_bass: boolean;
  };
}

export interface RazorpayOrderResponse {
  id: string;
  amount: number;
  currency: string;
  receipt: string;
  key_id: string;
  plan_id: string;
  customer_name?: string;
  customer_email?: string;
}
