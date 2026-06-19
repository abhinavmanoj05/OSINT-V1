-- Initialize PostgreSQL with required extensions and initial data

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create initial admin user (password: admin123 - change in production!)
-- This is a placeholder - use proper authentication in production
INSERT INTO cases (case_number, title, description, crime_type, status, priority, assigned_officer)
VALUES 
('KER/2024/00000', 'System Test Case', 'Initial system test case', 'Test', 'closed', 1, 'System')
ON CONFLICT (case_number) DO NOTHING;