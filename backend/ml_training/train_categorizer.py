import os
import re
import json
import joblib
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report, confusion_matrix

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    # Normalize reference numbers and transaction IDs
    text = re.sub(r'ref:[a-f0-9]+', 'ref_id', text)
    text = re.sub(r'inr\s*[\d\.,]+', 'inr_amount', text)
    text = re.sub(r'usd\s*[\d\.,]+', 'usd_amount', text)
    text = re.sub(r'[\d]{4,}', 'num_token', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_business_training_samples():
    """Augment the dataset with business-oriented transactions to cover standard SME chart of accounts."""
    business_samples = [
        # Software & Cloud Services
        ("AWS EMEA Cloud Hosting monthly compute", "Software & Cloud Services"),
        ("Amazon Web Services cloud infrastructure billing", "Software & Cloud Services"),
        ("Google Cloud Platform EMEA compute invoice", "Software & Cloud Services"),
        ("Microsoft Azure monthly subscription", "Software & Cloud Services"),
        ("Slack Technologies monthly business plan", "Software & Cloud Services"),
        ("Zoom Video Communications subscription", "Software & Cloud Services"),
        ("GitHub Enterprise seat billing", "Software & Cloud Services"),
        ("Atlassian Jira Confluence subscription", "Software & Cloud Services"),
        ("HubSpot CRM monthly subscription tier", "Software & Cloud Services"),
        ("Notion Labs workspace billing", "Software & Cloud Services"),
        ("Figma design seat subscription monthly", "Software & Cloud Services"),
        ("Vercel Pro hosting tier invoice", "Software & Cloud Services"),
        ("Datadog monitoring and APM license", "Software & Cloud Services"),
        ("OpenAI API platform platform usage charge", "Software & Cloud Services"),
        ("Anthropic Claude API usage billing", "Software & Cloud Services"),
        ("MongoDB Atlas database cluster hosting", "Software & Cloud Services"),
        ("SendGrid email delivery service", "Software & Cloud Services"),
        ("Twilio SMS verification and messaging", "Software & Cloud Services"),
        
        # Payroll & Benefits
        ("Gusto payroll processing direct deposit batch", "Payroll & Wages"),
        ("Rippling employee salaries disbursement", "Payroll & Wages"),
        ("ADP TotalSource payroll tax and wages", "Payroll & Wages"),
        ("Employee salary transfer Oct 2026", "Payroll & Wages"),
        ("Direct deposit payroll employee wages", "Payroll & Wages"),
        ("Bi-weekly payroll distribution direct deposit", "Payroll & Wages"),
        ("Contractor invoice payout Upwork escrow", "Payroll & Wages"),
        ("Deel contractor international payout", "Payroll & Wages"),
        ("Health insurance premium BlueCross BlueShield", "Payroll & Wages"),
        ("401k employee retirement contribution match", "Payroll & Wages"),
        
        # Office & Rent
        ("WeWork monthly dedicated office rent", "Rent & Facilities"),
        ("Regus executive office suite rental", "Rent & Facilities"),
        ("Commercial property lease payment building management", "Rent & Facilities"),
        ("Building maintenance and janitorial services", "Rent & Facilities"),
        ("Office electricity utility Consolidated Edison", "Rent & Facilities"),
        ("High-speed fiber commercial internet Comcast Business", "Rent & Facilities"),
        ("Water and municipal utility quarterly bill", "Rent & Facilities"),
        
        # Marketing & Sales
        ("Google Ads online search campaigns advertising", "Marketing & Advertising"),
        ("Facebook Meta Ads business manager promotion", "Marketing & Advertising"),
        ("LinkedIn Sponsored content campaigns marketing", "Marketing & Advertising"),
        ("Twitter X Ads business campaign invoice", "Marketing & Advertising"),
        ("Mailchimp email newsletter marketing automation", "Marketing & Advertising"),
        ("Canva Pro commercial design marketing", "Marketing & Advertising"),
        ("Conference booth sponsorship expo fee", "Marketing & Advertising"),
        ("PR Newswire press release distribution", "Marketing & Advertising"),
        
        # Professional Services & Legal
        ("Wilson Sonsini Goodrich & Rosati legal advisory", "Professional & Legal"),
        ("Deloitte tax compliance and audit advisory", "Professional & Legal"),
        ("Accounting book-keeping monthly retainer fee", "Professional & Legal"),
        ("Stripe Atlas entity incorporation legal fee", "Professional & Legal"),
        ("Patent trademark filing USPTO legal retainer", "Professional & Legal"),
        
        # Income / Revenue
        ("Stripe payout merchant transfer client settlement", "Client Revenue"),
        ("Shopify Payments deposit daily merchant earnings", "Client Revenue"),
        ("Inbound wire client invoice INV-2026-081 paid", "Client Revenue"),
        ("ACH credit enterprise customer annual license payment", "Client Revenue"),
        ("Customer subscription receipt wire transfer", "Client Revenue"),
        ("Consulting retainer service payment received", "Client Revenue"),
        ("B2B SaaS enterprise contract Q4 payment", "Client Revenue")
    ]
    return pd.DataFrame(business_samples, columns=["Transaction_Text", "Label"])

def train_and_evaluate():
    kaggle_dir = r"C:\Users\LENOVO\.cache\kagglehub\datasets\coderanand\indian-banking-transaction-text-dataset\versions\1"
    train_file = os.path.join(kaggle_dir, "financial_transaction_train.csv")
    test_file = os.path.join(kaggle_dir, "financial_transaction_test.csv")
    
    print(f"Loading Kaggle dataset from {kaggle_dir}...")
    train_df = pd.read_csv(train_file)
    test_df = pd.read_csv(test_file)
    
    # Map Kaggle labels to standard business financial categories
    category_map = {
        "Food": "Meals & Entertainment",
        "Shopping": "Office Supplies & Equipment",
        "Travel": "Travel & Transportation",
        "Investment": "Investment & Capital",
        "EMI": "Loans & Financing"
    }
    
    train_df["Label"] = train_df["Label"].map(lambda x: category_map.get(x, x))
    test_df["Label"] = test_df["Label"].map(lambda x: category_map.get(x, x))
    
    # Add business samples
    biz_df = get_business_training_samples()
    # Duplicate business samples 5x to ensure good representation alongside Kaggle 10k rows
    biz_augmented = pd.concat([biz_df] * 10, ignore_index=True)
    full_train_df = pd.concat([train_df, biz_augmented], ignore_index=True)
    
    # Preprocess text
    X_train_raw = full_train_df["Transaction_Text"].fillna("").astype(str)
    y_train = full_train_df["Label"]
    
    X_test_raw = test_df["Transaction_Text"].fillna("").astype(str)
    y_test = test_df["Label"]
    
    X_train_clean = [clean_text(t) for t in X_train_raw]
    X_test_clean = [clean_text(t) for t in X_test_raw]
    
    print(f"Total training samples: {len(X_train_clean)}")
    print(f"Total testing samples: {len(X_test_clean)}")
    
    # TF-IDF Vectorizer with unigrams and bigrams
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=2,
        max_features=15000
    )
    
    X_train_vec = vectorizer.fit_transform(X_train_clean)
    X_test_vec = vectorizer.transform(X_test_clean)
    
    # Train Logistic Regression with class probabilities
    model = LogisticRegression(
        C=2.0,
        max_iter=1000,
        class_weight="balanced",
        random_state=42
    )
    model.fit(X_train_vec, y_train)
    
    # Predictions and evaluation
    y_pred = model.predict(X_test_vec)
    y_proba = model.predict_proba(X_test_vec)
    
    acc = accuracy_score(y_test, y_pred)
    prec, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="weighted", zero_division=0)
    prec_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(y_test, y_pred, average="macro", zero_division=0)
    
    labels_order = sorted(list(set(y_test)))
    cm = confusion_matrix(y_test, y_pred, labels=labels_order)
    
    print("\n" + "="*50)
    print(f"MODEL EVALUATION REPORT on Indian Banking Test Set (N={len(y_test)}):")
    print(f"Accuracy:  {acc * 100:.2f}%")
    print(f"Precision (Weighted): {prec * 100:.2f}%")
    print(f"Recall (Weighted):    {recall * 100:.2f}%")
    print(f"F1-Score (Weighted):  {f1 * 100:.2f}%")
    print(f"F1-Score (Macro):     {f1_macro * 100:.2f}%")
    print("="*50)
    
    report_dict = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    
    # Prepare artifact directory
    out_dir = os.path.join(os.path.dirname(__file__), "..", "ml_models")
    os.makedirs(out_dir, exist_ok=True)
    
    model_version = "v1.2.0-kaggle-tfidf-logreg"
    
    # Save model and vectorizer
    model_artifact = {
        "model": model,
        "vectorizer": vectorizer,
        "model_version": model_version,
        "classes": list(model.classes_),
        "clean_function_version": "v1"
    }
    model_path = os.path.join(out_dir, "categorizer.joblib")
    joblib.dump(model_artifact, model_path)
    print(f"Trained model saved to: {model_path}")
    
    # Save evaluation report JSON
    eval_report = {
        "model_version": model_version,
        "dataset": "Indian Banking Transaction Text Dataset + SME Extensions",
        "train_samples_count": len(X_train_clean),
        "test_samples_count": len(X_test_clean),
        "accuracy": float(acc),
        "weighted_precision": float(prec),
        "weighted_recall": float(recall),
        "weighted_f1": float(f1),
        "macro_f1": float(f1_macro),
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": labels_order,
        "per_class_report": report_dict
    }
    
    eval_path = os.path.join(out_dir, "evaluation_report.json")
    with open(eval_path, "w") as f:
        json.dump(eval_report, f, indent=2)
    print(f"Evaluation report saved to: {eval_path}")
    
    # Quick sanity test on sample queries
    test_queries = [
        "Swiggy food order online",
        "Uber cab fare to airport",
        "Amazon Web Services monthly bill",
        "Gusto payroll direct deposit",
        "HDFC home loan monthly EMI",
        "Stripe payout customer invoice"
    ]
    print("\nSanity Predictions:")
    for q in test_queries:
        vec = vectorizer.transform([clean_text(q)])
        pred = model.predict(vec)[0]
        conf = float(np.max(model.predict_proba(vec)))
        print(f" - '{q}' -> {pred} (Confidence: {conf*100:.1f}%)")

if __name__ == "__main__":
    train_and_evaluate()
