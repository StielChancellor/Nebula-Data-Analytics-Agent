###############################################################################
# Identity Platform / Firebase Auth (Phase 1.5) — gated on enable_identity_platform.
#
# The backend verifies Firebase ID tokens regardless of this (dual-mode auth),
# so this is only needed to actually issue tokens to real users.
#
# NOTE: the very first Identity Platform enablement on a project sometimes
# requires a one-time "Get Started" click in the GCP/Firebase console — the
# API can't always self-initialize. If `terraform apply` errors with
# "CONFIGURATION_NOT_FOUND" or similar, click through once, then re-apply.
# See docs/PHASE-1.5-STATUS.md.
###############################################################################

resource "google_identity_platform_config" "default" {
  count    = var.enable_identity_platform ? 1 : 0
  provider = google-beta
  project  = var.project_id

  sign_in {
    allow_duplicate_emails = false

    email {
      enabled           = true
      password_required = true
    }
  }

  depends_on = [google_project_service.enabled]
}

# A default tenant so multi-tenant tokens carry firebase.tenant. Brands map to
# tenants. (Identity Platform multi-tenancy must be enabled on the project —
# creating a tenant enables it; if it errors, enable multi-tenancy in console.)
resource "google_identity_platform_tenant" "default" {
  count                 = var.enable_identity_platform && var.enable_identity_platform_tenant ? 1 : 0
  provider              = google-beta
  display_name          = "default"
  allow_password_signup = true

  depends_on = [google_identity_platform_config.default]
}

# Browser API key for the Firebase web SDK (VITE_FIREBASE_API_KEY).
resource "google_apikeys_key" "firebase_web" {
  count        = var.enable_identity_platform ? 1 : 0
  name         = "insnav-firebase-web"
  display_name = "Insights Navigator — Firebase web API key"

  restrictions {
    # Tighten allowed_referrers to your brand domains before production.
    browser_key_restrictions {
      allowed_referrers = ["*"]
    }
    api_targets {
      service = "identitytoolkit.googleapis.com"
    }
  }

  depends_on = [google_project_service.enabled]
}
